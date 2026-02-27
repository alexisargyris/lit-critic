/**
 * lit-critic — VS Code Extension entry point.
 *
 * Orchestrates all components:
 *   - ServerManager: spawns/stops the FastAPI backend
 *   - ApiClient: typed HTTP wrapper for the REST API
 *   - DiagnosticsProvider: maps findings to squiggly underlines
 *   - FindingsTreeProvider: sidebar tree view of all findings
 *   - DiscussionPanel: webview for interactive discussion
 *   - StatusBar: quick status overview
 */

import * as vscode from 'vscode';
import * as path from 'path';

import { ServerManager } from './serverManager';
import { ApiClient } from './apiClient';
import { DiagnosticsProvider } from './diagnosticsProvider';
import { FindingsDecorationProvider, FindingsTreeProvider } from './findingsTreeProvider';
import { SessionsTreeProvider } from './sessionsTreeProvider';
import { LearningTreeProvider } from './learningTreeProvider';
import { DiscussionPanel } from './discussionPanel';
import { StatusBar } from './statusBar';
import { OperationTracker } from './operationTracker';
import { REPO_MARKER, validateRepoPath } from './repoPreflight';
import { tryParseRepoPathInvalidDetail } from './domain/sessionDecisionLogic';
import {
    Finding,
    AnalysisSummary,
    ResumeErrorDetail,
    ScenePathRecoverySelection,
} from './types';
import { createRuntimeStateStore } from './workflows/stateStore';
import { WorkbenchPresenter } from './ui/workbenchPresenter';
import { StartupService } from './bootstrap/startupService';
import { registerCommands } from './commands/registerCommands';
import {
    SessionWorkflowController,
    WorkflowDeps,
    WorkflowUiPort,
} from './workflows/sessionWorkflowController';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let serverManager: ServerManager | undefined;
let apiClient: ApiClient;
let diagnosticsProvider: DiagnosticsProvider;
let findingsTreeProvider: FindingsTreeProvider;
let findingsDecorationProvider: FindingsDecorationProvider;
let sessionsTreeProvider: SessionsTreeProvider;
let learningTreeProvider: LearningTreeProvider;
let findingsTreeView: vscode.TreeView<any> | undefined;
let sessionsTreeView: vscode.TreeView<any> | undefined;
let discussionPanel: DiscussionPanel;
let statusBar: StatusBar;
let operationTracker: OperationTracker;
let presenter: WorkbenchPresenter;
let startupService: StartupService;
let controller: SessionWorkflowController;

const state = createRuntimeStateStore();

// ---------------------------------------------------------------------------
// Activation
// ---------------------------------------------------------------------------

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // Always initialize UI components so the sidebar tree view is registered,
    // even when the lit-critic repo root is not found (e.g. user opened
    // a scene folder rather than the repo itself).
    statusBar = new StatusBar();
    operationTracker = new OperationTracker();
    diagnosticsProvider = new DiagnosticsProvider();
    findingsDecorationProvider = new FindingsDecorationProvider();
    findingsTreeProvider = new FindingsTreeProvider(findingsDecorationProvider);
    sessionsTreeProvider = new SessionsTreeProvider();
    learningTreeProvider = new LearningTreeProvider();

    // Register tree views — must always happen so VS Code can populate the sidebar
    findingsTreeView = vscode.window.createTreeView('literaryCritic.findings', {
        treeDataProvider: findingsTreeProvider,
        showCollapseAll: true,
    });

    sessionsTreeView = vscode.window.createTreeView('literaryCritic.sessions', {
        treeDataProvider: sessionsTreeProvider,
        showCollapseAll: true,
    });

    presenter = new WorkbenchPresenter({
        statusBar,
        diagnosticsProvider,
        findingsTreeProvider,
        sessionsTreeProvider,
        ensureDiscussionPanel,
        getDiscussionPanel: () => discussionPanel,
    });
    presenter.bindTreeViews(findingsTreeView, sessionsTreeView);

    // Initialize StartupService with concrete VS Code and filesystem ports.
    // Ports are created here (inside activate) so that test stubs injected via
    // proxyquire (e.g. vscode, fs) are captured correctly by the closures.
    const _fsModule = require('fs') as typeof import('fs');
    startupService = new StartupService({
        getConfiguredRepoPath: () =>
            vscode.workspace.getConfiguration('literaryCritic').get<string>('repoPath', '').trim(),
        getAutoStartEnabled: () =>
            vscode.workspace.getConfiguration('literaryCritic').get<boolean>('autoStartServer', true),
        updateConfiguredRepoPath: (value) =>
            Promise.resolve(vscode.workspace.getConfiguration('literaryCritic').update(
                'repoPath', value, vscode.ConfigurationTarget.Global,
            )),
        pathExists: (p) => _fsModule.existsSync(p),
        getWorkspaceFolders: () =>
            vscode.workspace.workspaceFolders as Array<{ uri: { fsPath: string } }> | undefined,
        showErrorModal: (msg, ...buttons) =>
            vscode.window.showErrorMessage(msg, { modal: true }, ...(buttons as [string, ...string[]])) as Promise<string | undefined>,
        showFolderPicker: async () => {
            const picked = await vscode.window.showOpenDialog({
                canSelectFiles: false,
                canSelectFolders: true,
                canSelectMany: false,
                openLabel: 'Use this folder',
            });
            return picked?.[0]?.fsPath;
        },
        openSettings: (key) =>
            vscode.commands.executeCommand('workbench.action.openSettings', key) as Promise<void>,
        getConfiguredRepoPathAfterSettingsEdit: () =>
            vscode.workspace.getConfiguration('literaryCritic').get<string>('repoPath', '').trim(),
        withProgressNotification: (title, message, task) =>
            vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title, cancellable: false },
                async (progress) => { progress.report({ message }); await task(); },
            ) as Promise<void>,
        executeCommand: (cmd) =>
            vscode.commands.executeCommand(cmd) as Promise<void>,
    });

    const learningTreeView = vscode.window.createTreeView('literaryCritic.learning', {
        treeDataProvider: learningTreeProvider,
        showCollapseAll: true,
    });

    // Register all disposables
    context.subscriptions.push(
        statusBar,
        operationTracker,
        diagnosticsProvider,
        vscode.window.registerFileDecorationProvider(findingsDecorationProvider),
        findingsTreeView,
        sessionsTreeView,
        learningTreeView,
    );

    const findingsVisibilityDisposable = findingsTreeView.onDidChangeVisibility?.((event) => {
        if (event.visible) {
            presenter.revealCurrentFindingSelection();
        }
    });
    if (findingsVisibilityDisposable) {
        context.subscriptions.push(findingsVisibilityDisposable);
    }

    const sessionsVisibilityDisposable = sessionsTreeView.onDidChangeVisibility?.((event) => {
        if (event.visible) {
            presenter.revealCurrentSessionSelection();
        }
    });
    if (sessionsVisibilityDisposable) {
        context.subscriptions.push(sessionsVisibilityDisposable);
    }

    // Build WorkflowUiPort adapter — maps the controller's narrow interface to
    // real VS Code APIs. Created inside activate() so proxyquire stubs are
    // captured correctly by the closures.
    const _fsForUi = require('fs') as typeof import('fs');
    const uiPort: WorkflowUiPort = {
        showInformationMessage: (msg, ...items) =>
            vscode.window.showInformationMessage(msg, ...items) as Promise<string | undefined>,
        showErrorMessage: (msg, ...items) =>
            vscode.window.showErrorMessage(msg, ...items) as Promise<string | undefined>,
        showWarningMessage: (msg, modal, ...items) =>
            vscode.window.showWarningMessage(
                msg, { modal }, ...(items as [string, ...string[]])
            ) as Promise<string | undefined>,
        showInputBox: (opts) => vscode.window.showInputBox(opts) as Promise<string | undefined>,
        showQuickPick: async (items, opts) => {
            if (!opts?.activeItemLabel || typeof (vscode.window as any).createQuickPick !== 'function') {
                return vscode.window.showQuickPick(items, {
                    placeHolder: opts?.placeHolder,
                }) as Promise<any>;
            }

            const qp = (vscode.window as any).createQuickPick();
            qp.items = items as any[];
            qp.placeholder = opts.placeHolder;

            const activeItem = (items as any[]).find((item: any) => {
                const label = typeof item === 'string' ? item : item?.label;
                return label === opts.activeItemLabel;
            });
            if (activeItem) {
                qp.activeItems = [activeItem];
            }

            return await new Promise<any>((resolve) => {
                let settled = false;

                const acceptDisp = qp.onDidAccept(() => {
                    if (settled) {
                        return;
                    }
                    settled = true;
                    const selected = qp.selectedItems?.[0] ?? qp.activeItems?.[0];
                    acceptDisp.dispose();
                    hideDisp.dispose();
                    qp.dispose();
                    resolve(selected);
                });

                const hideDisp = qp.onDidHide(() => {
                    if (settled) {
                        return;
                    }
                    settled = true;
                    acceptDisp.dispose();
                    hideDisp.dispose();
                    qp.dispose();
                    resolve(undefined);
                });

                qp.show();
            });
        },
        showOpenDialog: (opts) =>
            vscode.window.showOpenDialog(opts) as unknown as Promise<Array<{ fsPath: string }> | undefined>,
        showTextDocument: (fsPath, opts) =>
            vscode.window.showTextDocument(vscode.Uri.file(fsPath), {
                viewColumn: opts?.viewColumn as vscode.ViewColumn | undefined,
                preview: opts?.preview,
                preserveFocus: opts?.preserveFocus,
            }) as Promise<any>,
        withProgress: (title, task) =>
            vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title, cancellable: false },
                async (progress) => { await task(progress); },
            ) as Promise<void>,
        setStatusBarMessage: (msg, timeout) =>
            vscode.window.setStatusBarMessage(msg, timeout),
        navigateToFindingLine: (finding) => navigateToFindingLine(finding),
        pathExists: (p) => _fsForUi.existsSync(p),
        getOpenTextDocumentPaths: () => {
            const paths = new Set<string>();
            const tabGroups = (vscode.window as any).tabGroups?.all;

            if (Array.isArray(tabGroups)) {
                for (const group of tabGroups) {
                    const tabs = Array.isArray(group?.tabs) ? group.tabs : [];
                    for (const tab of tabs) {
                        const input: any = tab?.input;
                        const candidateUris: Array<any> = [
                            input?.uri,
                            input?.modified,
                            input?.modified?.uri,
                            input?.original,
                            input?.original?.uri,
                        ];

                        for (const uri of candidateUris) {
                            if (uri?.scheme === 'file' && typeof uri.fsPath === 'string' && uri.fsPath.length > 0) {
                                paths.add(uri.fsPath);
                            }
                        }
                    }
                }
            }

            // Fallback for test stubs / older hosts where tabGroups may be unavailable.
            if (paths.size === 0) {
                for (const editor of vscode.window.visibleTextEditors) {
                    const fsPath = editor?.document?.uri?.fsPath;
                    if (typeof fsPath === 'string' && fsPath.length > 0) {
                        paths.add(fsPath);
                    }
                }
            }

            return Array.from(paths);
        },
        getExtensionConfig: () =>
            vscode.workspace.getConfiguration('literaryCritic') as any,
    };

    // Build WorkflowDeps and instantiate the controller.
    const workflowDeps: WorkflowDeps = {
        getApiClient: () => ensureApiClient(),
        ensureServer: () => ensureServer(),
        getServerManager: () => serverManager,
        state,
        presenter,
        findingsTreeProvider,
        sessionsTreeProvider,
        learningTreeProvider,
        diagnosticsProvider,
        ensureDiscussionPanel: () => ensureDiscussionPanel(),
        getDiscussionPanel: () => discussionPanel,
        runTrackedOperation: (profile, op) => runTrackedOperation(profile, op),
        detectProjectPath: () => detectProjectPath(),
        promptForScenePathOverride: (detail) => promptForScenePathOverride(detail),
        ui: uiPort,
    };
    controller = new SessionWorkflowController(workflowDeps);

    // Register all commands through the centralised registrar.
    // Must always happen so Command Palette entries are available.
    registerCommands(context.subscriptions, {
        cmdAnalyze: controller.cmdAnalyze,
        cmdResume: controller.cmdResume,
        cmdNextFinding: controller.cmdNextFinding,
        cmdAcceptFinding: controller.cmdAcceptFinding,
        cmdRejectFinding: controller.cmdRejectFinding,
        cmdDiscuss: controller.cmdDiscuss,
        cmdSelectFinding: controller.cmdSelectFinding,
        cmdReviewFinding: controller.cmdReviewFinding,
        cmdClearSession: controller.cmdClearSession,
        cmdRerunAnalysis: controller.cmdRerunAnalysis,
        cmdSelectModel: controller.cmdSelectModel,
        cmdStopServer: controller.cmdStopServer,
        cmdRefreshSessions: controller.cmdRefreshSessions,
        cmdViewSession: controller.cmdViewSession,
        cmdDeleteSession: controller.cmdDeleteSession,
        cmdRefreshLearning: controller.cmdRefreshLearning,
        cmdExportLearning: controller.cmdExportLearning,
        cmdResetLearning: controller.cmdResetLearning,
        cmdDeleteLearningEntry: controller.cmdDeleteLearningEntry,
    });

    const config = vscode.workspace.getConfiguration('literaryCritic');
    const autoStartServer = config.get<boolean>('autoStartServer', true);
    const activationStartupHint = autoStartServer
        ? vscode.window.setStatusBarMessage('lit-critic: Preparing startup...', 5000)
        : undefined;

    // Apply workspace-scoped problem-decoration preferences (optional).
    await applyWorkspaceProblemDecorationPreferences();

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((event) => {
            if (
                event.affectsConfiguration('literaryCritic.disableProblemDecorationColors')
                || event.affectsConfiguration('literaryCritic.disableProblemDecorationBadges')
            ) {
                void applyWorkspaceProblemDecorationPreferences();
            }
        })
    );

    let repoRoot = findRepoRoot();
    if (!repoRoot && autoStartServer) {
        const configuredRepoPath = config.get<string>('repoPath', '').trim();
        const configuredValidation = validateRepoPath(configuredRepoPath || undefined);

        if (configuredRepoPath && !configuredValidation.ok) {
            try {
                repoRoot = await ensureRepoRootWithRecovery();
            } catch {
                repoRoot = undefined;
            }
        }
    }

    try {
        if (repoRoot) {
            serverManager = new ServerManager(repoRoot);
            context.subscriptions.push(serverManager);

            if (autoStartServer) {
                try {
                    await startServerWithBusyUi(repoRoot);
                    await autoLoadSidebar();
                    await revealLitCriticActivityContainerIfProjectDetected();
                } catch (err) {
                    const msg = err instanceof Error ? err.message : String(err);
                    presenter.setError(msg);
                }
            }
        }
    } finally {
        activationStartupHint?.dispose();
    }
}

export function deactivate(): void {
    discussionPanel?.dispose();
    serverManager?.stop();
}

async function applyWorkspaceProblemDecorationPreferences(): Promise<void> {
    const config = vscode.workspace.getConfiguration('literaryCritic');
    const disableColors = config.get<boolean>('disableProblemDecorationColors', false);
    const disableBadges = config.get<boolean>('disableProblemDecorationBadges', false);

    const workbenchConfig = vscode.workspace.getConfiguration('workbench');

    await workbenchConfig.update(
        'editor.decorations.colors',
        disableColors ? false : undefined,
        vscode.ConfigurationTarget.Workspace,
    );

    await workbenchConfig.update(
        'editor.decorations.badges',
        disableBadges ? false : undefined,
        vscode.ConfigurationTarget.Workspace,
    );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function findRepoRoot(): string | undefined {
    const config = vscode.workspace.getConfiguration('literaryCritic');
    const configured = config.get<string>('repoPath', '').trim();
    if (configured) {
        const validation = validateRepoPath(configured);
        if (validation.ok) {
            return validation.path || configured;
        }
    }
    return findRepoRootFromWorkspace();
}

function findRepoRootFromWorkspace(): string | undefined {
    const fs = require('fs');
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
        return undefined;
    }

    for (const folder of workspaceFolders) {
        let dir = folder.uri.fsPath;
        for (let i = 0; i < 5; i++) {
            const marker = path.join(dir, REPO_MARKER);
            try {
                if (fs.existsSync(marker)) {
                    return dir;
                }
            } catch {
                // ignore
            }
            const parent = path.dirname(dir);
            if (parent === dir) { break; }
            dir = parent;
        }
    }

    return undefined;
}

async function startServerWithBusyUi(repoRoot: string): Promise<void> {
    presenter.setAnalyzing('Starting server...');
    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: 'lit-critic: Starting server',
            cancellable: false,
        },
        async (progress) => {
            progress.report({ message: 'Launching lit-critic backend...' });
            await serverManager!.start();
        },
    );

    await ensureApiClient().updateRepoPath(repoRoot).catch(() => {
        // Non-fatal
    });

    presenter.setReady();
}

async function ensureRepoRootWithRecovery(): Promise<string> {
    const config = vscode.workspace.getConfiguration('literaryCritic');
    const configured = config.get<string>('repoPath', '').trim();
    const configuredValidation = validateRepoPath(configured || undefined);
    if (configuredValidation.ok) {
        return configuredValidation.path || configured;
    }

    const workspaceRoot = findRepoRootFromWorkspace();
    if (workspaceRoot) {
        const workspaceValidation = validateRepoPath(workspaceRoot);
        if (workspaceValidation.ok) {
            return workspaceValidation.path || workspaceRoot;
        }
    }

    let currentMessage = configured
        ? configuredValidation.message
        : `Could not locate lit-critic installation (${REPO_MARKER}).`;

    while (true) {
        const action = await vscode.window.showErrorMessage(
            `lit-critic startup preflight failed. ${currentMessage}`,
            { modal: true },
            'Select Folder…',
            'Open Settings',
            'Cancel',
        );

        if (action === 'Cancel' || !action) {
            throw new Error('Repository path setup cancelled.');
        }

        if (action === 'Open Settings') {
            await vscode.commands.executeCommand('workbench.action.openSettings', 'literaryCritic.repoPath');
            const candidate = vscode.workspace.getConfiguration('literaryCritic').get<string>('repoPath', '').trim();
            const validation = validateRepoPath(candidate || undefined);
            if (validation.ok) {
                return validation.path || candidate;
            }
            currentMessage = validation.message;
            continue;
        }

        const picked = await vscode.window.showOpenDialog({
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            openLabel: 'Use this folder',
        });
        if (!picked || picked.length === 0) {
            currentMessage = `No folder selected. Please choose a directory containing ${REPO_MARKER}.`;
            continue;
        }

        const selected = picked[0].fsPath;
        const validation = validateRepoPath(selected);
        if (!validation.ok) {
            currentMessage = validation.message;
            continue;
        }

        const normalized = validation.path || selected;
        await vscode.workspace.getConfiguration('literaryCritic').update(
            'repoPath',
            normalized,
            vscode.ConfigurationTarget.Global,
        );
        return normalized;
    }
}

function detectProjectPath(): string | undefined {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
        return undefined;
    }

    const fs = require('fs');
    for (const folder of workspaceFolders) {
        const canonPath = path.join(folder.uri.fsPath, 'CANON.md');
        if (fs.existsSync(canonPath)) {
            return folder.uri.fsPath;
        }
    }

    return undefined;
}

async function autoLoadSidebar(): Promise<void> {
    await runTrackedOperation(
        {
            id: 'auto-load-sidebar',
            title: 'Loading sessions and learning data',
            statusMessage: 'Loading sessions and learning data...',
        },
        async () => {
            const projectPath = detectProjectPath();
            if (!projectPath) {
                return;
            }

            const client = ensureApiClient();

            sessionsTreeProvider.setApiClient(client);
            sessionsTreeProvider.setProjectPath(projectPath);
            await sessionsTreeProvider.refresh().catch(() => {});

            learningTreeProvider.setApiClient(client);
            learningTreeProvider.setProjectPath(projectPath);
            await learningTreeProvider.refresh().catch(() => {});

            try {
                const sessionInfo = await client.getSession();
                sessionsTreeProvider.setCurrentSessionByScenePath(
                    sessionInfo.active ? sessionInfo.scene_path : undefined,
                );
                presenter.revealCurrentSessionSelection();
                if (sessionInfo.active && sessionInfo.scene_path) {
                    const summary = await resumeWithScenePathRecovery(client, projectPath);

                    if (!summary.error) {
                        await populateFindingsAfterAnalysis(summary);
                        presenter.setProgress(summary.current_index + 1, summary.total_findings);
                    }
                }
            } catch {
                // Silently ignore — user can manually resume if needed
            }
        },
    );
}

async function revealLitCriticActivityContainerIfProjectDetected(): Promise<void> {
    const projectPath = detectProjectPath();
    if (!projectPath) {
        return;
    }

    try {
        await vscode.commands.executeCommand('workbench.view.extension.lit-critic');
    } catch {
        // Non-fatal
    }
}

async function ensureServer(): Promise<void> {
    const startupHint = vscode.window.setStatusBarMessage('lit-critic: Preparing startup...', 5000);
    const repoRoot = await ensureRepoRootWithRecovery();

    if (!serverManager) {
        serverManager = new ServerManager(repoRoot);
    } else {
        const existingRoot = serverManager.repoRoot;
        if (existingRoot && existingRoot !== repoRoot) {
            serverManager.dispose();
            serverManager = new ServerManager(repoRoot);
            apiClient = new ApiClient(serverManager.baseUrl);
        }
    }

    if (serverManager.isRunning) {
        await ensureApiClient().updateRepoPath(repoRoot).catch(() => {});
        return;
    }

    try {
        await startServerWithBusyUi(repoRoot);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        presenter.setError(msg);
        throw new Error(`Could not start lit-critic server: ${msg}`);
    } finally {
        startupHint.dispose();
    }
}

function ensureApiClient(): ApiClient {
    if (!apiClient) {
        if (!serverManager) {
            throw new Error('Server not initialized. Run "lit-critic: Analyze" first.');
        }
        apiClient = new ApiClient(serverManager.baseUrl);
    }
    return apiClient;
}

function ensureDiscussionPanel(): DiscussionPanel {
    if (!discussionPanel) {
        discussionPanel = new DiscussionPanel(ensureApiClient());
        discussionPanel.onFindingAction = controller.handleFindingAction;
        discussionPanel.onDiscussionResult = (result) => {
            void controller.handleDiscussionResult(result);
        };
    }
    return discussionPanel;
}

async function runTrackedOperation<T>(
    profile: {
        id: string;
        title: string;
        statusMessage?: string;
        slowThresholdMs?: number;
        progressThresholdMs?: number;
    },
    operation: () => Promise<T>,
): Promise<T> {
    if (!operationTracker) {
        return operation();
    }
    return operationTracker.run(profile, operation);
}

async function navigateToFindingLine(finding: Finding): Promise<void> {
    if (finding.line_start === null) {
        return;
    }

    const scenePath = finding.scene_path || diagnosticsProvider.scenePath;
    if (!scenePath) {
        return;
    }

    const line = Math.max(0, finding.line_start - 1);
    const endLine = Math.max(0, (finding.line_end || finding.line_start) - 1);
    const range = new vscode.Range(line, 0, endLine, 0);

    const scenePathLower = scenePath.toLowerCase();
    const existingEditor = vscode.window.visibleTextEditors.find(
        e => e.document.uri.fsPath.toLowerCase() === scenePathLower
    );

    if (existingEditor) {
        existingEditor.selection = new vscode.Selection(range.start, range.end);
        existingEditor.revealRange(range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    } else {
        const uri = vscode.Uri.file(scenePath);
        await vscode.window.showTextDocument(uri, {
            viewColumn: vscode.ViewColumn.One,
            selection: range,
            preserveFocus: true,
        });
    }
}

async function populateFindingsAfterAnalysis(summary: AnalysisSummary): Promise<void> {
    const client = ensureApiClient();

    let findingsStatus = summary.findings_status;

    if (!findingsStatus) {
        console.warn('lit-critic: findings_status not in analysis response, falling back to GET /api/session');
        try {
            const session = await client.getSession();
            if (!session.active || !session.findings_status) {
                console.error('lit-critic: Failed to load findings from session endpoint');
                vscode.window.showErrorMessage('lit-critic: Could not load findings. Try resuming the session.');
                return;
            }
            findingsStatus = session.findings_status;
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            console.error('lit-critic: Error fetching session:', msg);
            vscode.window.showErrorMessage(`lit-critic: Could not load findings — ${msg}`);
            return;
        }
    }

    state.allFindings = findingsStatus.map((f) => ({
        number: f.number,
        severity: f.severity as 'critical' | 'major' | 'minor',
        lens: f.lens,
        location: f.location,
        line_start: f.line_start ?? null,
        line_end: f.line_end ?? null,
        scene_path: (f as any).scene_path ?? null,
        evidence: f.evidence ?? '',
        impact: '',
        options: [],
        flagged_by: [],
        ambiguity_type: null,
        stale: false,
        status: f.status,
    }));

    state.totalFindings = state.allFindings.length;
    findingsTreeProvider.setFindings(state.allFindings, summary.scene_path, summary.current_index);
    presenter.revealCurrentFindingSelection();
    diagnosticsProvider.setScenePath(summary.scene_path, summary.scene_paths);

    try {
        const firstFinding = await client.getCurrentFinding();
        if (!firstFinding.complete && firstFinding.finding) {
            updateCachedFinding(firstFinding.finding);
            diagnosticsProvider.updateFromFindings(state.allFindings);
        }
    } catch (err) {
        console.warn('lit-critic: Could not fetch first finding details:', err);
    }
}

function updateCachedFinding(finding: Finding): void {
    const idx = state.allFindings.findIndex(f => f.number === finding.number);
    if (idx >= 0) {
        state.allFindings[idx] = finding;
    } else {
        state.allFindings.push(finding);
    }
    findingsTreeProvider.updateFinding(finding);
    diagnosticsProvider.updateFromFindings(state.allFindings);
}

// ---------------------------------------------------------------------------
// Recovery helpers used by autoLoadSidebar and controller deps
// ---------------------------------------------------------------------------

async function promptForScenePathOverride(detail: ResumeErrorDetail): Promise<ScenePathRecoverySelection | undefined> {
    const savedPaths = detail.saved_scene_paths && detail.saved_scene_paths.length > 0
        ? detail.saved_scene_paths
        : (detail.saved_scene_path ? [detail.saved_scene_path] : []);
    const missingPaths = detail.missing_scene_paths && detail.missing_scene_paths.length > 0
        ? detail.missing_scene_paths
        : (detail.attempted_scene_path ? [detail.attempted_scene_path] : []);

    if (missingPaths.length > 1) {
        const overrides: Record<string, string> = {};
        for (const missingPath of missingPaths) {
            const defaultUri = missingPath ? vscode.Uri.file(missingPath) : undefined;
            const picked = await vscode.window.showOpenDialog({
                canSelectFiles: true,
                canSelectFolders: false,
                canSelectMany: false,
                openLabel: 'Map this scene file',
                title: `Scene missing: ${path.basename(missingPath)} — select replacement file`,
                defaultUri,
            });

            const selected = picked?.[0]?.fsPath;
            if (!selected) {
                return undefined;
            }
            overrides[missingPath] = selected;
        }

        return { scenePathOverrides: overrides };
    }

    const fallback = missingPaths[0] || savedPaths[0] || detail.saved_scene_path || detail.attempted_scene_path || '';
    const defaultUri = fallback ? vscode.Uri.file(fallback) : undefined;

    const picked = await vscode.window.showOpenDialog({
        canSelectFiles: true,
        canSelectFolders: false,
        canSelectMany: false,
        openLabel: 'Resume with this file',
        title: 'Scene file not found — select the correct file to resume',
        defaultUri,
    });

    const selected = picked?.[0]?.fsPath;
    if (!selected) {
        return undefined;
    }

    return { scenePathOverride: selected };
}

async function resumeWithScenePathRecovery(client: ApiClient, projectPath: string): Promise<AnalysisSummary> {
    try {
        return await client.resumeWithRecovery(
            projectPath,
            undefined,
            promptForScenePathOverride,
        );
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        const detail = tryParseRepoPathInvalidDetail(message);
        const repoRoot = serverManager?.repoRoot;
        if (!detail || !repoRoot) {
            throw err;
        }

        await client.updateRepoPath(repoRoot);
        return client.resumeWithRecovery(
            projectPath,
            undefined,
            promptForScenePathOverride,
        );
    }
}
