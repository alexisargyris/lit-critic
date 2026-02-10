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
import { FindingsTreeProvider } from './findingsTreeProvider';
import { DiscussionPanel } from './discussionPanel';
import { StatusBar } from './statusBar';
import { Finding, AnalysisSummary, FindingResponse, AdvanceResponse } from './types';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let serverManager: ServerManager | undefined;
let apiClient: ApiClient;
let diagnosticsProvider: DiagnosticsProvider;
let findingsTreeProvider: FindingsTreeProvider;
let discussionPanel: DiscussionPanel;
let statusBar: StatusBar;

/** All findings from the current session (full objects with line numbers). */
let allFindings: Finding[] = [];
let currentFindingIndex = 0;
let totalFindings = 0;

// ---------------------------------------------------------------------------
// Activation
// ---------------------------------------------------------------------------

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // Always initialize UI components so the sidebar tree view is registered,
    // even when the lit-critic repo root is not found (e.g. user opened
    // a scene folder rather than the repo itself).
    statusBar = new StatusBar();
    diagnosticsProvider = new DiagnosticsProvider();
    findingsTreeProvider = new FindingsTreeProvider();

    // Register tree view — must always happen so VS Code can populate the sidebar
    const treeView = vscode.window.createTreeView('literaryCritic.findings', {
        treeDataProvider: findingsTreeProvider,
        showCollapseAll: true,
    });

    // Register all disposables
    context.subscriptions.push(
        statusBar,
        diagnosticsProvider,
        treeView,
    );

    // Register commands — must always happen so Command Palette entries work
    context.subscriptions.push(
        vscode.commands.registerCommand('literaryCritic.analyze', cmdAnalyze),
        vscode.commands.registerCommand('literaryCritic.resume', cmdResume),
        vscode.commands.registerCommand('literaryCritic.nextFinding', cmdNextFinding),
        vscode.commands.registerCommand('literaryCritic.acceptFinding', cmdAcceptFinding),
        vscode.commands.registerCommand('literaryCritic.rejectFinding', cmdRejectFinding),
        vscode.commands.registerCommand('literaryCritic.discuss', cmdDiscuss),
        vscode.commands.registerCommand('literaryCritic.selectFinding', cmdSelectFinding),
        vscode.commands.registerCommand('literaryCritic.skipMinor', cmdSkipMinor),
        vscode.commands.registerCommand('literaryCritic.saveSession', cmdSaveSession),
        vscode.commands.registerCommand('literaryCritic.clearSession', cmdClearSession),
        vscode.commands.registerCommand('literaryCritic.saveLearning', cmdSaveLearning),
        vscode.commands.registerCommand('literaryCritic.selectModel', cmdSelectModel),
        vscode.commands.registerCommand('literaryCritic.stopServer', cmdStopServer),
    );

    // Try to locate the repo root now.  If found, create the server manager
    // eagerly and optionally auto-start.  If not found, defer — the server
    // manager will be created lazily when the user runs an analyze command.
    const repoRoot = findRepoRoot();
    if (repoRoot) {
        serverManager = new ServerManager(repoRoot);
        context.subscriptions.push(serverManager);

        // Auto-start server if configured
        const config = vscode.workspace.getConfiguration('literaryCritic');
        if (config.get<boolean>('autoStartServer', true)) {
            try {
                await serverManager.start();
            } catch (err) {
                const msg = err instanceof Error ? err.message : String(err);
                statusBar.setError(msg);
                // Don't block activation — user can start manually via analyze command
            }
        }
    }
}

export function deactivate(): void {
    discussionPanel?.dispose();
    serverManager?.stop();
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
    const fs = require('fs');

    // 1. Explicit setting
    const config = vscode.workspace.getConfiguration('literaryCritic');
    const configured = config.get<string>('repoPath', '').trim();
    if (configured) {
        const marker = path.join(configured, 'lit-critic-web.py');
        if (fs.existsSync(marker)) {
            return configured;
        }
        // Setting is set but invalid — warn
        vscode.window.showWarningMessage(
            `lit-critic: literaryCritic.repoPath "${configured}" does not contain lit-critic-web.py. ` +
            `Falling back to workspace discovery.`
        );
    }

    // 2. Walk up from workspace folders
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
        return undefined;
    }

    for (const folder of workspaceFolders) {
        let dir = folder.uri.fsPath;
        for (let i = 0; i < 5; i++) {
            const marker = path.join(dir, 'lit-critic-web.py');
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
 * Ensure the server manager exists and the server is running.
 *
 * If the ServerManager was not created at activation time (e.g. the user
 * opened a scene folder without the lit-critic repo in the workspace),
 * we retry `findRepoRoot()` now — the user may have configured
 * `literaryCritic.repoPath` since activation, or we prompt them to do so.
 */
async function ensureServer(): Promise<void> {
    // Lazily create the ServerManager if it wasn't found at activation
    if (!serverManager) {
        const repoRoot = findRepoRoot();
        if (!repoRoot) {
            const action = await vscode.window.showErrorMessage(
                'lit-critic: Cannot find the lit-critic installation ' +
                '(lit-critic-web.py). Please set the `literaryCritic.repoPath` setting ' +
                'to the directory where lit-critic is installed.',
                'Open Settings'
            );
            if (action === 'Open Settings') {
                await vscode.commands.executeCommand(
                    'workbench.action.openSettings',
                    'literaryCritic.repoPath'
                );
            }
            throw new Error(
                'lit-critic repo not found. Set literaryCritic.repoPath in settings.'
            );
        }
        serverManager = new ServerManager(repoRoot);
    }

    if (serverManager.isRunning) {
        return;
    }

    statusBar.setAnalyzing('Starting server...');
    try {
        await serverManager.start();
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setError(msg);
        throw new Error(`Could not start lit-critic server: ${msg}`);
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
    }
    return discussionPanel;
}

/**
 * Present a finding: update diagnostics, tree view, discussion panel, and status bar.
 */
function presentFinding(findingResp: FindingResponse): void {
    if (findingResp.complete) {
        statusBar.setComplete();
        vscode.window.showInformationMessage('lit-critic: All findings have been reviewed.');
        ensureDiscussionPanel().close();
        return;
    }

    if (!findingResp.finding) {
        return;
    }

    currentFindingIndex = findingResp.index ?? currentFindingIndex;
    totalFindings = findingResp.total ?? totalFindings;

    statusBar.setProgress(findingResp.current ?? currentFindingIndex + 1, totalFindings);
    findingsTreeProvider.setCurrentIndex(currentFindingIndex);

    // Show the discussion panel
    ensureDiscussionPanel().show(
        findingResp.finding,
        findingResp.current ?? currentFindingIndex + 1,
        totalFindings,
        findingResp.is_ambiguity ?? false
    );
}

/**
 * Handle advance response (from continue/accept/reject) — check for scene changes, present next finding.
 */
function handleAdvanceResponse(resp: AdvanceResponse): void {
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

    // Present the next finding
    presentFinding(resp);
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

    // The backend walks findings one at a time via GET /api/finding.
    // To populate diagnostics for ALL findings at once, we use GET /api/session
    // which includes findings_status (but not full finding objects).
    // For full data, we store what we got from the analysis result.
    const session = await client.getSession();
    if (!session.active || !session.findings_status) {
        return;
    }

    // We need full Finding objects. The session info has summary only.
    // The analysis endpoint returns total_findings but not the findings array directly.
    // We'll build partial findings from session info for the tree, and get full
    // finding data from the current finding endpoint as we navigate.
    // For MVP: populate the tree from session info; diagnostics update per-finding.

    // Store findings from session info (partial — for tree display)
    allFindings = session.findings_status.map((f, i) => ({
        number: f.number,
        severity: f.severity as 'critical' | 'major' | 'minor',
        lens: f.lens,
        location: f.location,
        line_start: f.line_start ?? null,
        line_end: f.line_end ?? null,
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
    diagnosticsProvider.setScenePath(summary.scene_path);

    // Get the first full finding to start
    const firstFinding = await client.getCurrentFinding();
    if (!firstFinding.complete && firstFinding.finding) {
        // Update our cached finding with full data
        updateCachedFinding(firstFinding.finding);
        diagnosticsProvider.updateFromFindings(allFindings);
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
        await ensureServer();
        const client = ensureApiClient();

        // Determine scene path (active editor)
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showErrorMessage('lit-critic: Open a scene file first.');
            return;
        }
        const scenePath = editor.document.uri.fsPath;

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
        if (existingSession.exists) {
            const choice = await vscode.window.showQuickPick(
                ['Resume existing session', 'Start new analysis'],
                { placeHolder: `Found saved session (${existingSession.total_findings} findings). Resume or start fresh?` }
            );
            if (choice === 'Resume existing session') {
                return cmdResume();
            }
        }

        // Select model
        const config = vscode.workspace.getConfiguration('literaryCritic');
        const model = config.get<string>('model', 'sonnet');

        // Start analysis
        statusBar.setAnalyzing('Running 5 lenses...');
        vscode.window.showInformationMessage('lit-critic: Starting analysis...');

        // Fire off analysis first (don't await yet) — the POST creates the
        // backend's analysis_progress tracker that the SSE endpoint needs.
        const analysisPromise = client.analyze(scenePath, projectPath, model);

        // Give the POST a moment to reach the server and initialise the
        // progress tracker before we open the SSE stream.
        await new Promise((r) => setTimeout(r, 250));

        // Now open the SSE progress stream
        const progressPromise = new Promise<void>((resolve) => {
            client.streamAnalysisProgress(
                (event) => {
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
                            resolve();
                            break;
                    }
                },
                resolve,
                (err) => {
                    // Progress stream error is non-fatal — analysis may still complete
                    resolve();
                },
            );
        });

        // Wait for the analysis to finish
        const summary = await analysisPromise;

        // Wait for progress stream to finish
        await progressPromise;

        if (summary.error) {
            statusBar.setError(summary.error);
            vscode.window.showErrorMessage(`lit-critic: Analysis failed — ${summary.error}`);
            return;
        }

        vscode.window.showInformationMessage(
            `lit-critic: Found ${summary.total_findings} findings ` +
            `(${summary.counts.critical} critical, ${summary.counts.major} major, ${summary.counts.minor} minor)`
        );

        // Populate UI
        await populateFindingsAfterAnalysis(summary);

        // Present the first finding
        const firstFinding = await client.getCurrentFinding();
        presentFinding(firstFinding);

    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setError(msg);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdResume(): Promise<void> {
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

        statusBar.setAnalyzing('Resuming session...');
        const summary = await client.resume(projectPath);

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

        const finding = await client.getCurrentFinding();
        presentFinding(finding);

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
        if (!finding.complete && finding.finding) {
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
        const resp = await client.gotoFinding(index);

        // Update cached finding with full data from the backend
        if (!resp.complete && resp.finding) {
            updateCachedFinding(resp.finding);

            // Navigate to the finding's line in the editor
            const finding = resp.finding;
            if (finding.line_start !== null) {
                const scenePath = diagnosticsProvider.scenePath;
                if (scenePath) {
                    const line = Math.max(0, finding.line_start - 1);
                    const endLine = Math.max(0, (finding.line_end || finding.line_start) - 1);
                    const range = new vscode.Range(line, 0, endLine, 0);

                    // If the file is already visible, just move the cursor —
                    // don't re-open it (which would create a new editor group).
                    // Use case-insensitive comparison for Windows paths.
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
            }
        }

        handleAdvanceResponse(resp);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdSkipMinor(): Promise<void> {
    try {
        const client = ensureApiClient();
        const resp = await client.skipMinor();
        presentFinding(resp);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdSaveSession(): Promise<void> {
    try {
        const client = ensureApiClient();
        const result = await client.saveSession();
        vscode.window.showInformationMessage(`lit-critic: Session saved to ${result.path}`);
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
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`lit-critic: ${msg}`);
    }
}

async function cmdSaveLearning(): Promise<void> {
    try {
        const client = ensureApiClient();
        const result = await client.saveLearning();
        vscode.window.showInformationMessage(`lit-critic: LEARNING.md saved to ${result.path}`);
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
            await wsConfig.update('model', selected.label, vscode.ConfigurationTarget.Workspace);
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
            await ensureApiClient().rejectFinding(data as string || '');
            // Update UI
            if (allFindings[currentFindingIndex]) {
                allFindings[currentFindingIndex].status = 'rejected';
                diagnosticsProvider.removeFinding(allFindings[currentFindingIndex].number);
                findingsTreeProvider.updateFinding(allFindings[currentFindingIndex]);
            }
            await cmdNextFinding();
            break;
        case 'continue':
            await cmdNextFinding();
            break;
        case 'skipMinor':
            await cmdSkipMinor();
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
        case 'saveSession':
            await cmdSaveSession();
            break;
        case 'saveLearning':
            await cmdSaveLearning();
            break;
    }
}
