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
import {
    Finding,
    DiscussionContextTransition,
    AnalysisSummary,
    FindingResponse,
    AdvanceResponse,
    DiscussResponse,
    IndexChangeReport,
    ResumeErrorDetail,
    CheckSessionResponse,
    SessionSummary,
    ServerConfig,
} from './types';

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

/** All findings from the current session (full objects with line numbers). */
let allFindings: Finding[] = [];
let currentFindingIndex = 0;
let totalFindings = 0;
let closedSessionNotice: string | undefined;
let indexChangeDismissed = false;

function cloneDiscussionTurns(turns?: Array<{ role: string; content: string }>): Array<{ role: string; content: string }> {
    return (turns || []).map((t) => ({ role: t.role, content: t.content }));
}

function hasFindingContextChanged(previous: Finding, next: Finding): boolean {
    return (
        previous.evidence !== next.evidence
        || previous.location !== next.location
        || previous.line_start !== next.line_start
        || previous.line_end !== next.line_end
        || previous.severity !== next.severity
        || previous.impact !== next.impact
    );
}

function tryParseRepoPathInvalidDetail(message: string): { code?: string; message?: string } | null {
    const match = message.match(/^HTTP\s+\d+:\s+(\{.*\})$/);
    if (!match) {
        return null;
    }

    try {
        const detail = JSON.parse(match[1]) as { code?: string; message?: string };
        if (detail && detail.code === 'repo_path_invalid') {
            return detail;
        }
    } catch {
        // ignore parse failures
    }

    return null;
}

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
            revealCurrentFindingSelection();
        }
    });
    if (findingsVisibilityDisposable) {
        context.subscriptions.push(findingsVisibilityDisposable);
    }

    const sessionsVisibilityDisposable = sessionsTreeView.onDidChangeVisibility?.((event) => {
        if (event.visible) {
            revealCurrentSessionSelection();
        }
    });
    if (sessionsVisibilityDisposable) {
        context.subscriptions.push(sessionsVisibilityDisposable);
    }

    // Register commands — must always happen so Command Palette entries work
    context.subscriptions.push(
        vscode.commands.registerCommand('literaryCritic.analyze', cmdAnalyze),
        vscode.commands.registerCommand('literaryCritic.resume', cmdResume),
        vscode.commands.registerCommand('literaryCritic.nextFinding', cmdNextFinding),
        vscode.commands.registerCommand('literaryCritic.acceptFinding', cmdAcceptFinding),
        vscode.commands.registerCommand('literaryCritic.rejectFinding', cmdRejectFinding),
        vscode.commands.registerCommand('literaryCritic.discuss', cmdDiscuss),
        vscode.commands.registerCommand('literaryCritic.selectFinding', cmdSelectFinding),
        vscode.commands.registerCommand('literaryCritic.reviewFinding', cmdReviewFinding),
        vscode.commands.registerCommand('literaryCritic.clearSession', cmdClearSession),
        vscode.commands.registerCommand('literaryCritic.rerunAnalysisWithUpdatedIndexes', cmdRerunAnalysis),
        vscode.commands.registerCommand('literaryCritic.selectModel', cmdSelectModel),
        vscode.commands.registerCommand('literaryCritic.stopServer', cmdStopServer),
        // Phase 2: Management commands
        vscode.commands.registerCommand('literaryCritic.refreshSessions', cmdRefreshSessions),
        vscode.commands.registerCommand('literaryCritic.viewSession', cmdViewSession),
        vscode.commands.registerCommand('literaryCritic.deleteSession', cmdDeleteSession),
        vscode.commands.registerCommand('literaryCritic.refreshLearning', cmdRefreshLearning),
        vscode.commands.registerCommand('literaryCritic.exportLearning', cmdExportLearning),
        vscode.commands.registerCommand('literaryCritic.resetLearning', cmdResetLearning),
        vscode.commands.registerCommand('literaryCritic.deleteLearningEntry', cmdDeleteLearningEntry),
    );

    const config = vscode.workspace.getConfiguration('literaryCritic');
    const autoStartServer = config.get<boolean>('autoStartServer', true);
    const activationStartupHint = autoStartServer
        ? vscode.window.setStatusBarMessage('lit-critic: Preparing startup...', 5000)
        : undefined;

    // Apply workspace-scoped problem-decoration preferences (optional).
    // This can suppress diagnostic-based tab/file tinting for this workspace.
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

    // Try to locate the repo root now. If found, create the server manager
    // eagerly and optionally auto-start.
    //
    // Recovery behavior:
    // - If auto-start is enabled and the user explicitly configured
    //   `literaryCritic.repoPath` but it is invalid, run the same interactive
    //   recovery flow used by command-time startup.
    // - This avoids a silent no-op activation when repoPath is misconfigured.
    // - If the user cancels recovery, activation still succeeds and commands
    //   remain available (server can be started later via commands).
    let repoRoot = findRepoRoot();
    if (!repoRoot && autoStartServer) {
        const configuredRepoPath = config.get<string>('repoPath', '').trim();
        const configuredValidation = validateRepoPath(configuredRepoPath || undefined);

        if (configuredRepoPath && !configuredValidation.ok) {
            try {
                repoRoot = await ensureRepoRootWithRecovery();
            } catch {
                // User cancelled recovery or setup failed; keep activation non-fatal.
                repoRoot = undefined;
            }
        }
    }

    try {
        if (repoRoot) {
            serverManager = new ServerManager(repoRoot);
            context.subscriptions.push(serverManager);

            // Auto-start server if configured
            if (autoStartServer) {
                try {
                    await startServerWithBusyUi(repoRoot);
                    // Auto-load sidebar after server is running
                    await autoLoadSidebar();
                    // If this workspace is a lit-critic project (CANON.md present),
                    // automatically reveal the lit-critic activity container.
                    await revealLitCriticActivityContainerIfProjectDetected();
                } catch (err) {
                    const msg = err instanceof Error ? err.message : String(err);
                    statusBar.setError(msg);
                    // Don't block activation — user can start manually via analyze command
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

    // When enabled, pin the workspace setting to false.
    // When disabled, remove the workspace override to restore normal behavior.
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

/**
 * Find the repo root (directory containing lit-critic-web.py).
 *
 * Resolution order:
 *   1. The `literaryCritic.repoPath` setting (explicit override — useful when
 *      the user opens a scene folder that is *not* inside the repo tree).
 *   2. Walk up from each workspace folder looking for `lit-critic-web.py`.
 */
function findRepoRoot(): string | undefined {
    // 1. Explicit setting
    const config = vscode.workspace.getConfiguration('literaryCritic');
    const configured = config.get<string>('repoPath', '').trim();
    if (configured) {
        const validation = validateRepoPath(configured);
        if (validation.ok) {
            return validation.path || configured;
        }
    }

    // 2. Walk up from workspace folders
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
    statusBar.setAnalyzing('Starting server...');
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

    // Keep repo-path sync best-effort and outside the startup progress UI so the
    // "Starting server" notification disappears as soon as the backend is ready.
    await ensureApiClient().updateRepoPath(repoRoot).catch(() => {
        // Non-fatal: commands also do on-demand recovery when needed.
    });

    // Startup busy text should only cover backend boot. Once boot completes,
    // return to the default idle state unless a subsequent flow (e.g. resume)
    // immediately sets a more specific status.
    statusBar.setReady();
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

/**
 * Detect the project path (directory containing CANON.md) from workspace.
 */
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

/**
 * Resolve which editor/document should be analyzed.
 *
 * Priority:
 *   1. Active text editor, if it is a file-backed document.
 *   2. Any visible file-backed editor (auto-activate it for clarity).
 *   3. Native file picker (open selected file and return its editor).
 */
/** Result from resolving scene file(s) for analysis. */
interface ResolvedSceneFiles {
    editor: vscode.TextEditor;
    /** All selected scene paths (length > 1 for multi-scene). */
    scenePaths: string[];
}

async function resolveSceneEditorForAnalyze(): Promise<ResolvedSceneFiles | undefined> {
    const selected = await vscode.window.showOpenDialog({
        canSelectFiles: true,
        canSelectFolders: false,
        canSelectMany: true,
        openLabel: 'Analyze Scene',
        title: 'Select scene file(s) to analyze',
    });

    if (!selected || selected.length === 0) {
        return undefined;
    }

    const allPaths = selected.map(uri => uri.fsPath);

    try {
        const firstEditor = await vscode.window.showTextDocument(selected[0], {
            preview: false,
            preserveFocus: false,
        });

        // Ensure all selected scene files are opened in tabs for multi-scene sessions.
        for (let i = 1; i < selected.length; i += 1) {
            await vscode.window.showTextDocument(selected[i], {
                preview: false,
                preserveFocus: true,
                viewColumn: firstEditor.viewColumn,
            });
        }

        return { editor: firstEditor, scenePaths: allPaths };
    } catch {
        return undefined;
    }
}

/**
 * Resolve configured analysis model with backward compatibility.
 *
 * Preferred key: literaryCritic.analysisModel
 * Legacy fallback: literaryCritic.model
 */
function getConfiguredAnalysisModel(config: vscode.WorkspaceConfiguration): string {
    const analysisInspect = config.inspect<string>('analysisModel');
    const analysisIsExplicitlySet = Boolean(
        analysisInspect && (
            analysisInspect.globalValue !== undefined ||
            analysisInspect.workspaceValue !== undefined ||
            analysisInspect.workspaceFolderValue !== undefined
        )
    );

    if (analysisIsExplicitlySet) {
        return config.get<string>('analysisModel', 'sonnet');
    }

    // Backward-compatible fallback for older workspaces using literaryCritic.model
    return config.get<string>('model', config.get<string>('analysisModel', 'sonnet'));
}

function buildAnalysisStartStatusMessage(lensPreset: string, serverConfig?: ServerConfig): string {
    const weights = serverConfig?.lens_presets?.[lensPreset];
    if (!weights) {
        return `Running analysis (${lensPreset} preset)...`;
    }

    const activeLensCount = Object.values(weights).filter((value) => Number(value) > 0).length;
    if (activeLensCount <= 0) {
        return `Running analysis (${lensPreset} preset)...`;
    }

    const lensWord = activeLensCount === 1 ? 'lens' : 'lenses';
    return `Running ${activeLensCount} ${lensWord} (${lensPreset} preset)...`;
}

type AnalyzeEntryAction =
    | { kind: 'start-new' }
    | { kind: 'resume-default' }
    | { kind: 'resume-by-id'; sessionId: number };

function formatSessionLabel(session: SessionSummary): string {
    return `#${session.id} — ${path.basename(session.scene_path)}`;
}

async function chooseAnalyzeEntryAction(
    client: ApiClient,
    projectPath: string,
    existingSession: CheckSessionResponse,
): Promise<AnalyzeEntryAction | null> {
    if (!existingSession.exists) {
        return { kind: 'start-new' };
    }

    let activeSessions: SessionSummary[] = [];
    try {
        const sessions = await client.listSessions(projectPath);
        activeSessions = sessions.sessions.filter((s) => s.status === 'active');
    } catch {
        // Non-fatal fallback to legacy single-session prompt.
    }

    if (activeSessions.length > 1) {
        const items: Array<vscode.QuickPickItem & { action: AnalyzeEntryAction }> = [
            ...activeSessions.map((session) => ({
                label: `Resume ${formatSessionLabel(session)}`,
                description: `Created ${session.created_at}`,
                detail: session.scene_path,
                action: { kind: 'resume-by-id', sessionId: session.id } as AnalyzeEntryAction,
            })),
            {
                label: 'Start new analysis',
                detail: 'Create a fresh session for the current scene.',
                action: { kind: 'start-new' },
            },
        ];

        const selected = await vscode.window.showQuickPick(items, {
            placeHolder: 'Multiple active sessions found. Choose one to resume, or start a new analysis.',
        });

        return selected?.action ?? null;
    }

    if (activeSessions.length === 1) {
        const active = activeSessions[0];
        const choice = await vscode.window.showQuickPick(
            [
                `Resume ${formatSessionLabel(active)}`,
                'Start new analysis',
            ],
            {
                placeHolder: `Found active session for ${path.basename(active.scene_path)}. Resume or start fresh?`,
            },
        );

        if (!choice) {
            return null;
        }

        return choice.startsWith('Resume ')
            ? { kind: 'resume-by-id', sessionId: active.id }
            : { kind: 'start-new' };
    }

    const sceneHint = existingSession.scene_path ? ` for ${path.basename(existingSession.scene_path)}` : '';
    const choice = await vscode.window.showQuickPick(
        ['Resume existing session', 'Start new analysis'],
        {
            placeHolder: `Found saved session${sceneHint}. Resume or start fresh?`,
        },
    );

    if (!choice) {
        return null;
    }

    if (choice === 'Resume existing session') {
        if (typeof existingSession.session_id === 'number') {
            return { kind: 'resume-by-id', sessionId: existingSession.session_id };
        }
        return { kind: 'resume-default' };
    }

    return { kind: 'start-new' };
}

/**
 * Auto-load sidebar views after server starts.
 * 
 * Loads sessions and learning data, and if there's an active session,
 * automatically resumes it with its findings displayed.
 */
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
                // No CANON.md found — can't auto-load
                return;
            }

            // Initialize API client
            const client = ensureApiClient();

            // Set up and refresh sessions tree
            sessionsTreeProvider.setApiClient(client);
            sessionsTreeProvider.setProjectPath(projectPath);
            await sessionsTreeProvider.refresh().catch(() => {
                // Silently ignore — non-critical
            });

            // Set up and refresh learning tree
            learningTreeProvider.setApiClient(client);
            learningTreeProvider.setProjectPath(projectPath);
            await learningTreeProvider.refresh().catch(() => {
                // Silently ignore — non-critical
            });

            // Check if there's an active session and auto-resume it
            try {
                const sessionInfo = await client.getSession();
                sessionsTreeProvider.setCurrentSessionByScenePath(
                    sessionInfo.active ? sessionInfo.scene_path : undefined,
                );
                revealCurrentSessionSelection();
                if (sessionInfo.active && sessionInfo.scene_path) {
                    // There's an active session — resume it silently
                    const summary = await resumeWithScenePathRecovery(client, projectPath);

                    if (!summary.error) {
                        // Populate findings tree
                        await populateFindingsAfterAnalysis(summary);

                        // Update status bar to show progress
                        statusBar.setProgress(summary.current_index + 1, summary.total_findings);

                        // Don't auto-open the discussion panel — let the user click a finding
                        // when they're ready
                    }
                }
            } catch {
                // Silently ignore — user can manually resume if needed
            }
        },
    );
}

/**
 * Reveal the lit-critic activity container when the current workspace
 * is a detected lit-critic project (CANON.md present).
 */
async function revealLitCriticActivityContainerIfProjectDetected(): Promise<void> {
    const projectPath = detectProjectPath();
    if (!projectPath) {
        return;
    }

    try {
        await vscode.commands.executeCommand('workbench.view.extension.lit-critic');
    } catch {
        // Non-fatal: failing to reveal the view should not block activation.
    }
}

/**
 * Ensure the server manager exists and the server is running.
 *
 * If the ServerManager was not created at activation time (e.g. the user
 * opened a scene folder without the lit-critic repo in the workspace),
 * we retry `findRepoRoot()` now — the user may have configured
 * `literaryCritic.repoPath` since activation, or we prompt them to do so.
 */
async function ensureServer(): Promise<void> {
    const startupHint = vscode.window.setStatusBarMessage('lit-critic: Preparing startup...', 5000);
    const repoRoot = await ensureRepoRootWithRecovery();

    // Lazily create (or rebind) ServerManager
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
        // Keep backend preflight config in sync with extension recovery state.
        await ensureApiClient().updateRepoPath(repoRoot).catch(() => {
            // Non-fatal: backend may still proceed if it already has a valid path.
        });
        return;
    }

    try {
        await startServerWithBusyUi(repoRoot);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setError(msg);
        throw new Error(`Could not start lit-critic server: ${msg}`);
    } finally {
        startupHint.dispose();
    }
}

/**
 * Ensure apiClient is initialized.
 */
function ensureApiClient(): ApiClient {
    if (!apiClient) {
        if (!serverManager) {
            throw new Error('Server not initialized. Run "lit-critic: Analyze" first.');
        }
        apiClient = new ApiClient(serverManager.baseUrl);
    }
    return apiClient;
}

/**
 * Ensure the discussion panel is initialized.
 */
function ensureDiscussionPanel(): DiscussionPanel {
    if (!discussionPanel) {
        discussionPanel = new DiscussionPanel(ensureApiClient());
        discussionPanel.onFindingAction = handleFindingAction;
        discussionPanel.onDiscussionResult = (result) => {
            void handleDiscussionResult(result);
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

function isTerminalFindingStatus(status?: string): boolean {
    return status === 'accepted' || status === 'rejected' || status === 'withdrawn';
}

function getSafeTotalFindings(): number {
    return totalFindings > 0 ? totalFindings : allFindings.length;
}

function resolveFallbackFinding(preferredIndex?: number): { finding: Finding; index: number } | null {
    if (allFindings.length === 0) {
        return null;
    }

    const candidates = [
        preferredIndex,
        currentFindingIndex,
        allFindings.length - 1,
    ];

    for (const candidate of candidates) {
        if (typeof candidate === 'number' && candidate >= 0 && candidate < allFindings.length) {
            return { finding: allFindings[candidate], index: candidate };
        }
    }

    return null;
}

function getLatestFindingStatus(result: DiscussResponse): string | undefined {
    return result.finding?.status || result.finding_status;
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

function revealCurrentFindingSelection(): void {
    const item = findingsTreeProvider?.getCurrentFindingItem?.();
    if (!findingsTreeView || typeof findingsTreeView.reveal !== 'function' || !item) {
        return;
    }

    const revealResult = findingsTreeView.reveal(item, {
        select: true,
        focus: false,
        expand: true,
    });
    void Promise.resolve(revealResult).catch(() => {
        // Non-fatal: tree may not be visible/materialized yet.
    });
}

function revealCurrentSessionSelection(): void {
    const item = sessionsTreeProvider?.getCurrentSessionItem?.();
    if (!sessionsTreeView || typeof sessionsTreeView.reveal !== 'function' || !item) {
        return;
    }

    const revealResult = sessionsTreeView.reveal(item, {
        select: true,
        focus: false,
        expand: true,
    });
    void Promise.resolve(revealResult).catch(() => {
        // Non-fatal: tree may not be visible/materialized yet.
    });
}

function resolvePresentedFindingIndex(
    findingResp: FindingResponse,
    preferredIndex?: number,
): number {
    let resolvedIndex: number | undefined;

    if (findingResp.finding) {
        const matchedIndex = allFindings.findIndex((f) => f.number === findingResp.finding!.number);
        if (matchedIndex >= 0) {
            resolvedIndex = matchedIndex;
        }
    }

    // Prefer explicit backend index only when we couldn't map by finding number.
    // In some resume/view flows the backend may return a stale or missing index
    // while still returning the correct finding payload.
    if (typeof resolvedIndex !== 'number' && typeof findingResp.index === 'number') {
        resolvedIndex = findingResp.index;
    }

    if (typeof resolvedIndex !== 'number' && typeof preferredIndex === 'number') {
        resolvedIndex = preferredIndex;
    }

    if (typeof resolvedIndex !== 'number') {
        resolvedIndex = currentFindingIndex;
    }

    if (allFindings.length <= 0) {
        return Math.max(0, resolvedIndex);
    }

    if (resolvedIndex < 0) {
        return 0;
    }
    if (resolvedIndex >= allFindings.length) {
        return allFindings.length - 1;
    }
    return resolvedIndex;
}

async function handleDiscussionResult(result: DiscussResponse): Promise<void> {
    if (result.error) {
        return;
    }

    handleIndexChangeReport(result.index_change ?? null);

    const activeFinding = allFindings[currentFindingIndex];
    if (!activeFinding) {
        return;
    }

    if (result.finding) {
        updateCachedFinding(result.finding);
    } else if (result.finding_status) {
        activeFinding.status = result.finding_status;
        findingsTreeProvider.updateFinding(activeFinding);

        if (isTerminalFindingStatus(result.finding_status)) {
            diagnosticsProvider.removeFinding(activeFinding.number);
        } else {
            diagnosticsProvider.updateSingleFinding(activeFinding);
        }
    }

    const latestStatus = getLatestFindingStatus(result);
    if (latestStatus && latestStatus !== 'pending') {
        await sessionsTreeProvider.refresh().catch(() => {
            // Non-fatal: tree can still be refreshed manually.
        });
        // Refresh learning tree: discussion outcomes (withdrawn/rejected/conceded)
        // write new preference entries to SQLite.  The tree must be re-queried
        // so the user sees the new entry without needing a manual refresh.
        await learningTreeProvider.refresh().catch(() => {
            // Non-fatal: user can refresh manually via the toolbar icon.
        });
    }
}

/**
 * Present a finding: update diagnostics, tree view, discussion panel, and status bar.
 */
function presentFinding(
    findingResp: FindingResponse,
    preferredIndex?: number,
    discussionTransition?: DiscussionContextTransition,
): void {
    if (findingResp.complete) {
        statusBar.setComplete();
        vscode.window.showInformationMessage('lit-critic: All findings have been reviewed.');

        const fallback = resolveFallbackFinding(preferredIndex);
        if (fallback) {
            currentFindingIndex = fallback.index;
            findingsTreeProvider.setCurrentIndex(currentFindingIndex);
            revealCurrentFindingSelection();

            const total = getSafeTotalFindings();
            ensureDiscussionPanel().show(
                fallback.finding,
                Math.min(total, currentFindingIndex + 1),
                total,
                fallback.finding.ambiguity_type !== null,
                discussionTransition,
            );
        }

        // Keep the discussion panel open even at completion.
        // Users may keep iterating on scene edits and press Review again,
        // so auto-closing here disrupts that loop and makes the UI feel
        // like it disappeared unexpectedly.
        return;
    }

    if (!findingResp.finding) {
        return;
    }

    currentFindingIndex = resolvePresentedFindingIndex(findingResp, preferredIndex);
    totalFindings = findingResp.total ?? totalFindings;

    statusBar.setProgress(findingResp.current ?? currentFindingIndex + 1, totalFindings);
    findingsTreeProvider.setCurrentIndex(currentFindingIndex);
    revealCurrentFindingSelection();

    // Show the discussion panel
    ensureDiscussionPanel().show(
        findingResp.finding,
        findingResp.current ?? currentFindingIndex + 1,
        totalFindings,
        findingResp.is_ambiguity ?? false,
        discussionTransition,
        closedSessionNotice,
    );
}

/**
 * Handle advance response (from continue/accept/reject) — check for scene changes, present next finding.
 */
function handleAdvanceResponse(resp: AdvanceResponse, preferredIndex?: number): void {
    // Handle scene change notification
    if (resp.scene_change) {
        const sc = resp.scene_change;
        vscode.window.showInformationMessage(
            `📝 Scene change detected! Adjusted: ${sc.adjusted}, Stale: ${sc.stale}, Re-evaluated: ${sc.re_evaluated.length}`
        );
        ensureDiscussionPanel().notifySceneChange(sc);

        // Refresh all diagnostics after scene change
        refreshDiagnosticsFromSession();
    }

    handleIndexChangeReport(resp.index_change ?? null);

    // Present the next finding
    presentFinding(resp, preferredIndex);
}

function handleIndexChangeReport(report: IndexChangeReport | null | undefined): void {
    if (!report || !report.stale) {
        ensureDiscussionPanel().clearIndexChangeNotice();
        return;
    }

    if (report.prompt) {
        indexChangeDismissed = false;
    }

    if (!indexChangeDismissed) {
        ensureDiscussionPanel().notifyIndexChange(report);
    }

    if (report.prompt) {
        const changed = report.changed_files?.length ? report.changed_files.join(', ') : 'index context';
        void vscode.window.showWarningMessage(
            `lit-critic: ${changed} changed. Findings may be stale. Re-run analysis is recommended.`,
            'Re-run Analysis',
            'Dismiss',
        ).then(async (choice) => {
            if (choice === 'Re-run Analysis') {
                await cmdRerunAnalysis();
            } else if (choice === 'Dismiss') {
                indexChangeDismissed = true;
                ensureDiscussionPanel().clearIndexChangeNotice();
            }
        });
    }
}

/**
 * Refresh diagnostics by fetching the full session info.
 */
async function refreshDiagnosticsFromSession(): Promise<void> {
    try {
        const session = await ensureApiClient().getSession();
        if (session.active && session.findings_status) {
            // We need full finding data for diagnostics — use allFindings cache
            diagnosticsProvider.updateFromFindings(allFindings);
        }
    } catch {
        // Silently ignore — non-critical
    }
}

/**
 * After analysis completes, fetch all findings and populate diagnostics + tree.
 */
async function populateFindingsAfterAnalysis(summary: AnalysisSummary): Promise<void> {
    const client = ensureApiClient();

    // Starting with the server-side fix, the analysis/resume responses now include
    // findings_status directly. Use that if available; fall back to GET /api/session
    // only if needed (for backward compatibility or edge cases).
    let findingsStatus = summary.findings_status;

    if (!findingsStatus) {
        // Fallback: fetch from session endpoint (old behavior)
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

    // Build partial Finding objects for the tree (full data comes from /api/finding as we navigate)
    allFindings = findingsStatus.map((f) => ({
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

    totalFindings = allFindings.length;
    findingsTreeProvider.setFindings(allFindings, summary.scene_path, summary.current_index);
    revealCurrentFindingSelection();
    diagnosticsProvider.setScenePath(summary.scene_path, summary.scene_paths);

    // Get the first full finding to start
    try {
        const firstFinding = await client.getCurrentFinding();
        if (!firstFinding.complete && firstFinding.finding) {
            // Update our cached finding with full data
            updateCachedFinding(firstFinding.finding);
            diagnosticsProvider.updateFromFindings(allFindings);
        }
    } catch (err) {
        // Non-fatal — tree is already populated
        console.warn('lit-critic: Could not fetch first finding details:', err);
    }
}

/**
 * Update a finding in our cache with full data from the API.
 */
function updateCachedFinding(finding: Finding): void {
    const idx = allFindings.findIndex(f => f.number === finding.number);
    if (idx >= 0) {
        allFindings[idx] = finding;
    } else {
        allFindings.push(finding);
    }
    findingsTreeProvider.updateFinding(finding);
    diagnosticsProvider.updateFromFindings(allFindings);
}

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

async function cmdAnalyze(): Promise<void> {
    try {
        closedSessionNotice = undefined;
        indexChangeDismissed = false;
        await ensureServer();
        const client = ensureApiClient();

        // Determine project path
        const projectPath = detectProjectPath();
        if (!projectPath) {
            vscode.window.showErrorMessage(
                'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
            );
            return;
        }

        // Check for existing session
        const existingSession = await client.checkSession(projectPath);
        const entryAction = await chooseAnalyzeEntryAction(client, projectPath, existingSession);
        if (!entryAction) {
            return;
        }

        if (entryAction.kind === 'resume-default') {
            return cmdResume();
        }

        if (entryAction.kind === 'resume-by-id') {
            statusBar.setAnalyzing('Resuming session...');
            const summary = await resumeSessionByIdWithScenePathRecovery(client, projectPath, entryAction.sessionId);

            if (summary.error) {
                statusBar.setError(summary.error);
                vscode.window.showErrorMessage(`lit-critic: Resume failed — ${summary.error}`);
                return;
            }

            vscode.window.showInformationMessage(
                `lit-critic: Resumed session — ${summary.total_findings} findings, ` +
                `continuing from #${summary.current_index + 1}`
            );

            await populateFindingsAfterAnalysis(summary);
            await sessionsTreeProvider.refresh();
            sessionsTreeProvider.setCurrentSession(entryAction.sessionId);
            revealCurrentSessionSelection();
            handleIndexChangeReport(summary.index_change ?? null);

            const finding = await client.getCurrentFinding();
            handleIndexChangeReport(finding.index_change ?? null);
            presentFinding(finding, summary.current_index);
            refreshManagementViews();
            return;
        }

        // Start-new analyses always use the picker so users can choose one or many files.
        const resolved = await resolveSceneEditorForAnalyze();
        if (!resolved) {
            vscode.window.showErrorMessage(
                'lit-critic: No scene file selected.'
            );
            return;
        }
        const scenePath = resolved.scenePaths[0];
        const scenePaths = resolved.scenePaths.length > 1 ? resolved.scenePaths : undefined;

        // Select model
        const config = vscode.workspace.getConfiguration('literaryCritic');
        const model = getConfiguredAnalysisModel(config);
        const discussionModel = config.get<string>('discussionModel', '') || undefined;
        const lensPreset = config.get<string>('lensPreset', 'balanced');

        // Start analysis
        const serverConfig = await client.getConfig().catch(() => undefined);
        statusBar.setAnalyzing(buildAnalysisStartStatusMessage(lensPreset, serverConfig));
        vscode.window.showInformationMessage('lit-critic: Starting analysis...');

        let firstProgressEventSeen = false;
        let resolveFirstProgressEvent: (() => void) | undefined;
        const firstProgressEventPromise = new Promise<void>((resolve) => {
            resolveFirstProgressEvent = resolve;
        });
        const markFirstProgressEvent = (): void => {
            if (firstProgressEventSeen) {
                return;
            }
            firstProgressEventSeen = true;
            resolveFirstProgressEvent?.();
            resolveFirstProgressEvent = undefined;
        };

        // Fire off analysis first (don't await yet) — the POST creates the
        // backend's analysis_progress tracker that the SSE endpoint needs.
        const analysisPromise = (async () => {
            try {
                return await client.analyze(
                    scenePath,
                    projectPath,
                    model,
                    discussionModel,
                    undefined,
                    { preset: lensPreset },
                    scenePaths,
                );
            } catch (err) {
                const message = err instanceof Error ? err.message : String(err);
                const detail = tryParseRepoPathInvalidDetail(message);
                if (!detail) {
                    throw err;
                }

                const repoRoot = serverManager?.repoRoot;
                if (!repoRoot) {
                    throw err;
                }

                await client.updateRepoPath(repoRoot);
                return client.analyze(
                    scenePath,
                    projectPath,
                    model,
                    discussionModel,
                    undefined,
                    { preset: lensPreset },
                    scenePaths,
                );
            }
        })();

        // Give the POST a moment to reach the server and initialise the
        // progress tracker before we open the SSE stream.
        await new Promise((r) => setTimeout(r, 250));

        // Now open the SSE progress stream
        const progressPromise = new Promise<void>((resolve) => {
            client.streamAnalysisProgress(
                (event) => {
                    markFirstProgressEvent();
                    switch (event.type) {
                        case 'status':
                            statusBar.setAnalyzing(event.message);
                            break;
                        case 'lens_complete':
                            statusBar.setAnalyzing(`✓ ${event.lens} complete`);
                            break;
                        case 'lens_error':
                            vscode.window.showWarningMessage(`lit-critic: ${event.lens} lens failed: ${event.message}`);
                            break;
                        case 'complete':
                            statusBar.setAnalyzing('Analysis complete!');
                            break;
                        case 'done':
                            markFirstProgressEvent();
                            resolve();
                            break;
                    }
                },
                () => {
                    markFirstProgressEvent();
                    resolve();
                },
                (err) => {
                    // Progress stream error is non-fatal — analysis may still complete
                    markFirstProgressEvent();
                    resolve();
                },
            );
        });

        await vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'lit-critic: Starting analysis',
                cancellable: false,
            },
            async (progress) => {
                progress.report({ message: 'Sending analysis request...' });
                await Promise.race([
                    firstProgressEventPromise,
                    analysisPromise.then(() => undefined),
                ]);
            },
        );

        // Wait for the analysis to finish
        const summary = await analysisPromise;

        // Wait for progress stream to finish
        await progressPromise;

        if (summary.error) {
            statusBar.setError(summary.error);
            vscode.window.showErrorMessage(`lit-critic: Analysis failed — ${summary.error}`);
            return;
        }

        let modelInfo = `Model: ${summary.model.label}`;
        if (summary.discussion_model) {
            modelInfo += ` · Discussion: ${summary.discussion_model.label}`;
        }

        vscode.window.showInformationMessage(
            `lit-critic: Found ${summary.total_findings} findings ` +
            `(${summary.counts.critical} critical, ${summary.counts.major} major, ${summary.counts.minor} minor) · ${modelInfo}`
        );

        // Populate UI
        await populateFindingsAfterAnalysis(summary);

        // Present the first finding
        const firstFinding = await client.getCurrentFinding();
        handleIndexChangeReport(firstFinding.index_change ?? null);
        presentFinding(firstFinding);

        // Refresh management views
        refreshManagementViews();

    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setError(msg);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdResume(): Promise<void> {
    try {
        closedSessionNotice = undefined;
        indexChangeDismissed = false;
        await runTrackedOperation(
            {
                id: 'resume-session',
                title: 'Resuming session',
                statusMessage: 'Resuming session...',
            },
            async () => {
                await ensureServer();
                const client = ensureApiClient();

                const projectPath = detectProjectPath();
                if (!projectPath) {
                    vscode.window.showErrorMessage(
                        'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                    );
                    return;
                }

                statusBar.setAnalyzing('Resuming session...');
                const summary = await resumeWithScenePathRecovery(client, projectPath);

                if (summary.error) {
                    statusBar.setError(summary.error);
                    vscode.window.showErrorMessage(`lit-critic: Resume failed — ${summary.error}`);
                    return;
                }

                vscode.window.showInformationMessage(
                    `lit-critic: Resumed session — ${summary.total_findings} findings, ` +
                    `continuing from #${summary.current_index + 1}`
                );

                await populateFindingsAfterAnalysis(summary);
                await sessionsTreeProvider.refresh();
                sessionsTreeProvider.setCurrentSessionByScenePath(summary.scene_path);
                revealCurrentSessionSelection();
                handleIndexChangeReport(summary.index_change ?? null);

                const finding = await client.getCurrentFinding();
                handleIndexChangeReport(finding.index_change ?? null);
                presentFinding(finding);

                // Refresh management views
                refreshManagementViews();
            },
        );

    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setError(msg);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdNextFinding(): Promise<void> {
    try {
        const client = ensureApiClient();
        const resp = await client.continueFinding();

        // Update cached finding if the response includes the new finding
        if (!resp.complete && resp.finding) {
            updateCachedFinding(resp.finding);
        }

        handleAdvanceResponse(resp);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdAcceptFinding(): Promise<void> {
    try {
        const client = ensureApiClient();
        const resp = await client.acceptFinding();

        // The accept response wraps {action, next}
        const next = resp.next ?? resp;

        // Remove accepted finding from diagnostics
        if (allFindings[currentFindingIndex]) {
            allFindings[currentFindingIndex].status = 'accepted';
            diagnosticsProvider.removeFinding(allFindings[currentFindingIndex].number);
            findingsTreeProvider.updateFinding(allFindings[currentFindingIndex]);
        }

        // Update cached finding from next response
        if (!next.complete && next.finding) {
            updateCachedFinding(next.finding);
        }

        handleAdvanceResponse(next);
        
        // Refresh sessions tree to show updated counts
        await sessionsTreeProvider.refresh();
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdRejectFinding(): Promise<void> {
    try {
        const reason = await vscode.window.showInputBox({
            prompt: 'Reason for rejecting this finding (optional)',
            placeHolder: 'e.g., This is intentional for voice consistency',
        });

        const client = ensureApiClient();
        const resp = await client.rejectFinding(reason || '');

        const next = resp.next ?? resp;

        // Remove rejected finding from diagnostics
        if (allFindings[currentFindingIndex]) {
            allFindings[currentFindingIndex].status = 'rejected';
            diagnosticsProvider.removeFinding(allFindings[currentFindingIndex].number);
            findingsTreeProvider.updateFinding(allFindings[currentFindingIndex]);
        }

        if (!next.complete && next.finding) {
            updateCachedFinding(next.finding);
        }

        handleAdvanceResponse(next);
        
        // Refresh sessions tree to show updated counts
        await sessionsTreeProvider.refresh();
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdDiscuss(): Promise<void> {
    // Just focus the discussion panel — the actual discussion happens via the webview
    ensureDiscussionPanel();
    const client = ensureApiClient();

    try {
        const finding = await client.getCurrentFinding();
        handleIndexChangeReport(finding.index_change ?? null);
        if (!finding.complete && finding.finding) {
            updateCachedFinding(finding.finding);
            ensureDiscussionPanel().show(
                finding.finding,
                finding.current ?? 1,
                finding.total ?? totalFindings,
                finding.is_ambiguity ?? false
            );
        }
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

/**
 * Select a specific finding by index — called when the user clicks a tree item.
 *
 * This is the main entry point for free (non-sequential) navigation:
 *   1. Tells the backend to jump to the given index (with scene-change check)
 *   2. Navigates to the line in the editor (if line info is available)
 *   3. Opens/updates the Discussion Panel for the selected finding
 */
async function cmdSelectFinding(index: number): Promise<void> {
    try {
        const client = ensureApiClient();
        currentFindingIndex = index;
        findingsTreeProvider.setCurrentIndex(currentFindingIndex);
        revealCurrentFindingSelection();

        let resp: AdvanceResponse;
        try {
            resp = await client.gotoFinding(index);
        } catch (gotoErr) {
            const cached = allFindings[index];
            if (!cached) {
                throw gotoErr;
            }

            await navigateToFindingLine(cached);
            ensureDiscussionPanel().show(
                cached,
                index + 1,
                getSafeTotalFindings(),
                cached.ambiguity_type !== null,
                undefined,
                closedSessionNotice,
            );
            return;
        }

        // Update cached finding with full data from the backend
        if (!resp.complete && resp.finding) {
            updateCachedFinding(resp.finding);
            await navigateToFindingLine(resp.finding);
        }

        handleAdvanceResponse(resp, index);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdReviewFinding(): Promise<void> {
    try {
        const client = ensureApiClient();
        const resp = await client.reviewFinding();
        handleIndexChangeReport(resp.index_change ?? null);
        let discussionTransition: DiscussionContextTransition | undefined;

        if (!resp.complete && resp.finding) {
            const previousFinding = allFindings[currentFindingIndex];
            if (
                previousFinding
                && previousFinding.number === resp.finding.number
                && resp.review?.changed
                && hasFindingContextChanged(previousFinding, resp.finding)
            ) {
                discussionTransition = {
                    previousFinding: {
                        ...previousFinding,
                        options: [...(previousFinding.options || [])],
                        flagged_by: [...(previousFinding.flagged_by || [])],
                        discussion_turns: cloneDiscussionTurns(previousFinding.discussion_turns),
                    },
                    previousTurns: cloneDiscussionTurns(previousFinding.discussion_turns),
                    note: 'Finding re-evaluated after scene edits. Starting a new discussion context.',
                };
            }

            updateCachedFinding(resp.finding);
        }

        // Defensive guard: if review reports completion but unresolved findings
        // still exist, recover by fetching the current finding instead of
        // closing the discussion UI.
        if (resp.complete) {
            try {
                const session = await client.getSession();
                const hasPending = Boolean(
                    session.active
                    && session.findings_status
                    && session.findings_status.some((f) => !isTerminalFindingStatus(f.status))
                );

                if (hasPending) {
                    const fallback = await client.getCurrentFinding();
                    if (!fallback.complete && fallback.finding) {
                        vscode.window.showWarningMessage(
                            'lit-critic: Review reported completion but pending findings remain. Restored current finding.'
                        );
                        presentFinding(fallback);
                        return;
                    }
                }
            } catch {
                // Non-fatal: if consistency check fails, fall back to original response.
            }
        }

        presentFinding(resp, undefined, discussionTransition);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdClearSession(): Promise<void> {
    try {
        const confirm = await vscode.window.showWarningMessage(
            'Delete saved session?',
            { modal: true },
            'Delete'
        );
        if (confirm !== 'Delete') {
            return;
        }

        const client = ensureApiClient();
        await client.clearSession();
        vscode.window.showInformationMessage('lit-critic: Session cleared.');

        // Reset UI
        diagnosticsProvider.clear();
        findingsTreeProvider.clear();
        statusBar.setReady();
        allFindings = [];
        closedSessionNotice = undefined;
        indexChangeDismissed = false;
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdSelectModel(): Promise<void> {
    try {
        await ensureServer();
        const client = ensureApiClient();
        const config = await client.getConfig();

        const items = Object.entries(config.available_models).map(([name, info]) => ({
            label: name,
            description: info.label,
            picked: name === config.default_model,
        }));

        const selected = await vscode.window.showQuickPick(items, {
            placeHolder: 'Select a model for analysis',
        });

        if (selected) {
            const wsConfig = vscode.workspace.getConfiguration('literaryCritic');
            await wsConfig.update('analysisModel', selected.label, vscode.ConfigurationTarget.Workspace);
            vscode.window.showInformationMessage(`lit-critic: Model set to ${selected.label}`);
        }
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

function cmdStopServer(): void {
    if (serverManager) {
        serverManager.stop();
        statusBar.setReady();
        vscode.window.showInformationMessage('lit-critic: Server stopped.');
    } else {
        vscode.window.showInformationMessage('lit-critic: No server is running.');
    }
}

/**
 * Handle finding actions from the discussion panel webview.
 */
async function handleFindingAction(action: string, data?: unknown): Promise<void> {
    switch (action) {
        case 'accept':
            await cmdAcceptFinding();
            break;
        case 'reject':
            // Keep discussion-panel reject behavior aligned with the command path
            // so state/cache/tree/session counters stay in sync.
            await cmdRejectFinding();
            break;
        case 'continue':
            await cmdNextFinding();
            break;
        case 'reviewFinding':
            await cmdReviewFinding();
            break;
        case 'ambiguity':
            try {
                await ensureApiClient().markAmbiguity(data as boolean);
                vscode.window.showInformationMessage(
                    `lit-critic: Marked as ${data ? 'intentional' : 'accidental'}`
                );
            } catch (err) {
                const msg = err instanceof Error ? err.message : String(err);
                vscode.window.showErrorMessage(`lit-critic: ${msg}`);
            }
            break;
        case 'exportLearning':
            await cmdExportLearning();
            break;
        case 'rerunAnalysis':
            await cmdRerunAnalysis();
            break;
        case 'dismissIndexChange':
            indexChangeDismissed = true;
            ensureDiscussionPanel().clearIndexChangeNotice();
            break;
    }
}

// ---------------------------------------------------------------------------
// Phase 2: Management command handlers
// ---------------------------------------------------------------------------

async function cmdRefreshSessions(): Promise<void> {
    try {
        await runTrackedOperation(
            {
                id: 'refresh-sessions',
                title: 'Refreshing sessions',
                statusMessage: 'Refreshing sessions...',
            },
            async () => {
                await ensureServer();
                const projectPath = detectProjectPath();
                if (!projectPath) {
                    vscode.window.showErrorMessage(
                        'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                    );
                    return;
                }

                ensureApiClient();
                sessionsTreeProvider.setApiClient(apiClient);
                sessionsTreeProvider.setProjectPath(projectPath);
                await sessionsTreeProvider.refresh();
            },
        );
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdViewSession(item: any): Promise<void> {
    try {
        await runTrackedOperation(
            {
                id: 'view-session',
                title: 'Loading session findings',
                statusMessage: 'Loading session findings...',
            },
            async () => {
                await ensureServer();
                const projectPath = detectProjectPath();
                if (!projectPath) {
                    vscode.window.showErrorMessage(
                        'lit-critic: Could not detect project directory.'
                    );
                    return;
                }

                // Handle both calling patterns:
                // 1. From context menu: receives SessionTreeItem object with session property
                // 2. From direct call: receives number or session object
                const sessionId = typeof item === 'number' ? item : item?.session?.id;

                if (!sessionId) {
                    vscode.window.showErrorMessage('lit-critic: Could not determine session ID.');
                    return;
                }

                const client = ensureApiClient();
                const detail = await client.getSessionDetail(sessionId, projectPath);

                // If this is an active session, resume it
                if (detail.status === 'active') {
                    closedSessionNotice = undefined;
                    indexChangeDismissed = false;
                    statusBar.setAnalyzing('Resuming session...');

                    // Explicit click on an active session should switch context directly
                    // without an additional confirmation modal.
                    vscode.window.setStatusBarMessage(
                        `lit-critic: Switching to ${path.basename(detail.scene_path)}...`,
                        2500,
                    );

                    // Resume the selected session FIRST — this may correct the scene path
                    // via the promptForScenePathOverride recovery flow.
                    const summary = await resumeSessionByIdWithScenePathRecovery(client, projectPath, sessionId);

                    if (summary.error) {
                        statusBar.setError(summary.error);
                        vscode.window.showErrorMessage(`lit-critic: Resume failed — ${summary.error}`);
                        return;
                    }

                    // Open the scene file using the (potentially corrected) path returned
                    // by the resume response.  detail.scene_path may still hold the old,
                    // wrong path when the user had to supply a path override above.
                    const resolvedScenePath = summary.scene_path || detail.scene_path;
                    const fs = require('fs');
                    if (fs.existsSync(resolvedScenePath)) {
                        const uri = vscode.Uri.file(resolvedScenePath);
                        await vscode.window.showTextDocument(uri, {
                            viewColumn: vscode.ViewColumn.One,
                            preview: false,
                        });
                    } else {
                        vscode.window.showWarningMessage(
                            `Scene file not found: ${resolvedScenePath}`
                        );
                    }

                    // Populate findings tree
                    await populateFindingsAfterAnalysis(summary);
                    await sessionsTreeProvider.refresh();
                    sessionsTreeProvider.setCurrentSession(sessionId);
                    revealCurrentSessionSelection();
                    handleIndexChangeReport(summary.index_change ?? null);

                    const currentFinding = await client.getCurrentFinding();
                    handleIndexChangeReport(currentFinding.index_change ?? null);
                    if (!currentFinding.complete && currentFinding.finding) {
                        updateCachedFinding(currentFinding.finding);
                    }
                    presentFinding(currentFinding, summary.current_index);

                    // Update status bar to show progress
                    statusBar.setProgress(summary.current_index + 1, summary.total_findings);

                    vscode.window.showInformationMessage(
                        `lit-critic: Resumed session — ${summary.total_findings} findings, ` +
                        `continuing from #${summary.current_index + 1}`
                    );

                    // Refresh management views
                    refreshManagementViews();
                } else {
                    const summary = await viewSessionByIdWithScenePathRecovery(client, projectPath, sessionId);

                    if (summary.error) {
                        statusBar.setError(summary.error);
                        vscode.window.showErrorMessage(`lit-critic: Load failed — ${summary.error}`);
                        return;
                    }

                    closedSessionNotice = `Viewing ${detail.status} session — actions will reopen it.`;

                    const resolvedScenePath = summary.scene_path || detail.scene_path;
                    const fs = require('fs');
                    if (fs.existsSync(resolvedScenePath)) {
                        const uri = vscode.Uri.file(resolvedScenePath);
                        await vscode.window.showTextDocument(uri, {
                            viewColumn: vscode.ViewColumn.One,
                            preview: false,
                        });
                    } else {
                        vscode.window.showWarningMessage(`Scene file not found: ${resolvedScenePath}`);
                    }

                    await populateFindingsAfterAnalysis(summary);
                    await sessionsTreeProvider.refresh();
                    sessionsTreeProvider.setCurrentSession(sessionId);
                    revealCurrentSessionSelection();
                    handleIndexChangeReport(summary.index_change ?? null);

                    const currentFinding = await client.getCurrentFinding();
                    handleIndexChangeReport(currentFinding.index_change ?? null);
                    if (!currentFinding.complete && currentFinding.finding) {
                        updateCachedFinding(currentFinding.finding);
                    }

                    const selectedIndex = Math.min(
                        Math.max(detail.current_index ?? 0, 0),
                        Math.max(0, summary.total_findings - 1),
                    );

                    presentFinding(currentFinding, selectedIndex);
                    statusBar.setProgress(selectedIndex + 1, summary.total_findings);

                    vscode.window.showInformationMessage(
                        `Viewing ${detail.status} session: ${summary.total_findings} findings`
                    );

                    refreshManagementViews();
                }
            },
        );

    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function promptForScenePathOverride(detail: ResumeErrorDetail): Promise<string | undefined> {
    const fallback = detail.saved_scene_path || detail.attempted_scene_path || '';

    return vscode.window.showInputBox({
        prompt: 'Saved scene path was not found. Enter corrected scene file path to resume.',
        value: fallback,
        ignoreFocusOut: true,
        validateInput: (value) => {
            if (!value.trim()) {
                return 'Path is required to resume this session.';
            }
            return null;
        },
    });
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

async function resumeSessionByIdWithScenePathRecovery(
    client: ApiClient,
    projectPath: string,
    sessionId: number,
): Promise<AnalysisSummary> {
    return client.resumeSessionByIdWithRecovery(
        projectPath,
        sessionId,
        undefined,
        promptForScenePathOverride,
    );
}

async function viewSessionByIdWithScenePathRecovery(
    client: ApiClient,
    projectPath: string,
    sessionId: number,
): Promise<AnalysisSummary> {
    return client.viewSessionWithRecovery(
        projectPath,
        sessionId,
        undefined,
        promptForScenePathOverride,
    );
}

async function cmdDeleteSession(item?: any): Promise<void> {
    try {
        await runTrackedOperation(
            {
                id: 'delete-session',
                title: 'Deleting session',
                statusMessage: 'Deleting session...',
            },
            async () => {
                const selectedItem = sessionsTreeView?.selection?.[0];
                const targetItem = item ?? selectedItem;

                // Handle both calling patterns:
                // 1. From context menu: receives SessionTreeItem object with session property
                // 2. From direct call: receives number
                // 3. From view title toolbar: no arg, use current tree selection
                const sessionId = typeof targetItem === 'number' ? targetItem : targetItem?.session?.id;

                if (!sessionId) {
                    vscode.window.showWarningMessage('lit-critic: Select a session in the Sessions view to delete.');
                    return;
                }

                const confirm = await vscode.window.showWarningMessage(
                    `Delete session #${sessionId}? This cannot be undone.`,
                    { modal: true },
                    'Delete'
                );

                if (confirm !== 'Delete') {
                    return;
                }

                await ensureServer();
                const projectPath = detectProjectPath();
                if (!projectPath) {
                    return;
                }

                const client = ensureApiClient();

                // Check if this is the currently active session
                const sessionInfo = await client.getSession();
                const isActiveSession = sessionInfo.active &&
                                        targetItem?.session?.status === 'active';

                await client.deleteSession(sessionId, projectPath);

                vscode.window.showInformationMessage(`lit-critic: Session #${sessionId} deleted.`);

                // If we deleted the active session, clear all UI components
                if (isActiveSession) {
                    diagnosticsProvider.clear();
                    findingsTreeProvider.clear();
                    statusBar.setReady();
                    allFindings = [];
                    currentFindingIndex = 0;
                    totalFindings = 0;
                    discussionPanel?.close();
                    sessionsTreeProvider.setCurrentSession(null);
                }

                // Refresh sessions tree
                await sessionsTreeProvider.refresh();
            },
        );

    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdRefreshLearning(): Promise<void> {
    try {
        await runTrackedOperation(
            {
                id: 'refresh-learning',
                title: 'Refreshing learning data',
                statusMessage: 'Refreshing learning data...',
            },
            async () => {
                await ensureServer();
                const projectPath = detectProjectPath();
                if (!projectPath) {
                    vscode.window.showErrorMessage(
                        'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                    );
                    return;
                }

                ensureApiClient();
                learningTreeProvider.setApiClient(apiClient);
                learningTreeProvider.setProjectPath(projectPath);
                await learningTreeProvider.refresh();
            },
        );
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdRerunAnalysis(): Promise<void> {
    try {
        await ensureServer();
        const client = ensureApiClient();

        const projectPath = detectProjectPath();
        if (!projectPath) {
            vscode.window.showErrorMessage(
                'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
            );
            return;
        }

        statusBar.setAnalyzing('Re-running analysis with updated indexes...');
        const summary = await client.rerunAnalysis(projectPath);
        if (summary.error) {
            statusBar.setError(summary.error);
            vscode.window.showErrorMessage(`lit-critic: Re-run failed — ${summary.error}`);
            return;
        }

        indexChangeDismissed = false;
        // Explicit re-run from the index-change prompt should dismiss the
        // current discussion panel/dialog before presenting refreshed results.
        discussionPanel?.close();

        await populateFindingsAfterAnalysis(summary);
        const firstFinding = await client.getCurrentFinding();
        presentFinding(firstFinding);
        refreshManagementViews();

        vscode.window.showInformationMessage('lit-critic: Analysis re-run completed with updated indexes.');
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setError(msg);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdExportLearning(): Promise<void> {
    try {
        await runTrackedOperation(
            {
                id: 'export-learning',
                title: 'Exporting learning data',
                statusMessage: 'Exporting learning data...',
            },
            async () => {
                await ensureServer();
                const projectPath = detectProjectPath();
                if (!projectPath) {
                    return;
                }

                const client = ensureApiClient();
                const result = await client.exportLearning(projectPath);

                vscode.window.showInformationMessage(`lit-critic: LEARNING.md exported to ${result.path}`);
            },
        );
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdResetLearning(): Promise<void> {
    try {
        await runTrackedOperation(
            {
                id: 'reset-learning',
                title: 'Resetting learning data',
                statusMessage: 'Resetting learning data...',
            },
            async () => {
                const confirm = await vscode.window.showWarningMessage(
                    'Reset all learning data? This will delete all preferences, blind spots, and resolutions. This cannot be undone.',
                    { modal: true },
                    'Reset'
                );

                if (confirm !== 'Reset') {
                    return;
                }

                await ensureServer();
                const projectPath = detectProjectPath();
                if (!projectPath) {
                    return;
                }

                const client = ensureApiClient();
                await client.resetLearning(projectPath);

                vscode.window.showInformationMessage('lit-critic: Learning data reset.');

                // Refresh learning tree
                await learningTreeProvider.refresh();
            },
        );

    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdDeleteLearningEntry(item: any): Promise<void> {
    try {
        await runTrackedOperation(
            {
                id: 'delete-learning-entry',
                title: 'Deleting learning entry',
                statusMessage: 'Deleting learning entry...',
            },
            async () => {
                // Handle both calling patterns:
                // 1. From context menu: receives tree item object with entry property
                // 2. From direct call: receives number
                const entryId = typeof item === 'number' ? item : item?.entry?.id;

                if (!entryId) {
                    vscode.window.showErrorMessage('lit-critic: Could not determine learning entry ID.');
                    return;
                }

                await ensureServer();
                const projectPath = detectProjectPath();
                if (!projectPath) {
                    return;
                }

                const client = ensureApiClient();
                await client.deleteLearningEntry(entryId, projectPath);

                vscode.window.showInformationMessage('lit-critic: Learning entry deleted.');

                // Refresh learning tree
                await learningTreeProvider.refresh();
            },
        );

    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

/**
 * Refresh management views (sessions and learning).
 */
function refreshManagementViews(): void {
    const projectPath = detectProjectPath();
    if (!projectPath || !apiClient) {
        return;
    }

    // Set up and refresh sessions tree
    sessionsTreeProvider.setApiClient(apiClient);
    sessionsTreeProvider.setProjectPath(projectPath);
    sessionsTreeProvider.refresh()
        .catch(() => {
            // Silently ignore — non-critical
        });

    // Set up and refresh learning tree
    learningTreeProvider.setApiClient(apiClient);
    learningTreeProvider.setProjectPath(projectPath);
    learningTreeProvider.refresh().catch(() => {
        // Silently ignore — non-critical
    });
}
