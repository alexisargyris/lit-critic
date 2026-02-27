/**
 * SessionWorkflowController — all session/finding command handlers.
 *
 * Extracted from extension.ts so that workflow behaviour can be unit-tested
 * without loading the VS Code runtime or calling activate().
 *
 * All VS Code interactions are injected through WorkflowUiPort.
 * All collaborator services are injected through WorkflowDeps.
 */

import * as path from 'path';

import { ApiClient } from '../apiClient';
import { DiagnosticsProvider } from '../diagnosticsProvider';
import { FindingsTreeProvider } from '../findingsTreeProvider';
import { SessionsTreeProvider } from '../sessionsTreeProvider';
import { LearningTreeProvider } from '../learningTreeProvider';
import { DiscussionPanel } from '../discussionPanel';
import {
    cloneDiscussionTurns,
    getLatestFindingStatus,
    getSafeTotalFindings,
    hasFindingContextChanged,
    isTerminalFindingStatus,
    resolveFallbackFinding,
    resolvePresentedFindingIndex,
} from '../domain/findingLogic';
import {
    buildAnalysisStartStatusMessage,
    getConfiguredAnalysisModel,
    resolvePreferredModel,
} from '../domain/modelSelectionLogic';
import { formatSessionLabel, tryParseRepoPathInvalidDetail } from '../domain/sessionDecisionLogic';
import {
    Finding,
    DiscussionContextTransition,
    AnalysisSummary,
    FindingResponse,
    AdvanceResponse,
    DiscussResponse,
    IndexChangeReport,
    ResumeErrorDetail,
    ScenePathRecoverySelection,
    CheckSessionResponse,
    SessionSummary,
} from '../types';
import { RuntimeStateStore } from './stateStore';
import { WorkbenchPresenter } from '../ui/workbenchPresenter';

// ---------------------------------------------------------------------------
// Port interface — VS Code surface injected by extension.ts
// ---------------------------------------------------------------------------

export interface WorkflowUiPort {
    // Messages
    showInformationMessage(message: string, ...items: string[]): Promise<string | undefined>;
    showErrorMessage(message: string, ...items: string[]): Promise<string | undefined>;
    showWarningMessage(message: string, modal: boolean, ...items: string[]): Promise<string | undefined>;

    // User inputs
    showInputBox(options: {
        prompt?: string;
        placeHolder?: string;
        value?: string;
        ignoreFocusOut?: boolean;
        validateInput?: (value: string) => string | null;
    }): Promise<string | undefined>;
    showQuickPick(items: any[], options?: { placeHolder?: string; activeItemLabel?: string }): Promise<any>;

    // File operations
    showOpenDialog(options: {
        canSelectFiles: boolean;
        canSelectFolders: boolean;
        canSelectMany: boolean;
        openLabel?: string;
        title?: string;
    }): Promise<Array<{ fsPath: string }> | undefined>;
    showTextDocument(fsPath: string, options?: {
        viewColumn?: number;
        preview?: boolean;
        preserveFocus?: boolean;
    }): Promise<any>;

    // Progress / status
    withProgress(title: string, task: (progress: { report(v: { message?: string }): void }) => Promise<void>): Promise<void>;
    setStatusBarMessage(message: string, timeout: number): { dispose(): void };

    // Navigation
    navigateToFindingLine(finding: Finding): Promise<void>;

    // Filesystem check
    pathExists(p: string): boolean;
    getOpenTextDocumentPaths(): string[];

    // Extension configuration
    getExtensionConfig(): {
        get<T>(key: string, defaultValue: T): T;
        inspect<T>(key: string): { globalValue?: T; workspaceValue?: T; workspaceFolderValue?: T } | undefined;
    };
}

// ---------------------------------------------------------------------------
// Deps interface — all collaborators injected by extension.ts
// ---------------------------------------------------------------------------

export interface WorkflowDeps {
    getApiClient(): ApiClient;
    ensureServer(): Promise<void>;
    getServerManager(): { stop(): void; isRunning: boolean; repoRoot?: string } | undefined;
    state: RuntimeStateStore;
    presenter: WorkbenchPresenter;
    findingsTreeProvider: FindingsTreeProvider;
    sessionsTreeProvider: SessionsTreeProvider;
    learningTreeProvider: LearningTreeProvider;
    diagnosticsProvider: DiagnosticsProvider;
    ensureDiscussionPanel(): DiscussionPanel;
    getDiscussionPanel(): DiscussionPanel | undefined;
    runTrackedOperation<T>(
        profile: { id: string; title: string; statusMessage?: string },
        operation: () => Promise<T>,
    ): Promise<T>;
    detectProjectPath(): string | undefined;
    promptForScenePathOverride(detail: ResumeErrorDetail): Promise<ScenePathRecoverySelection | undefined>;
    ui: WorkflowUiPort;
}

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------

type AnalyzeEntryAction =
    | { kind: 'start-new' }
    | { kind: 'resume-default' }
    | { kind: 'resume-by-id'; sessionId: number };

// ---------------------------------------------------------------------------
// Controller
// ---------------------------------------------------------------------------

export class SessionWorkflowController {
    constructor(private readonly deps: WorkflowDeps) {}

    // -----------------------------------------------------------------------
    // Public command handlers
    // -----------------------------------------------------------------------

    cmdAnalyze = async (): Promise<void> => { await this._cmdAnalyze(); };
    cmdResume = async (): Promise<void> => { await this._cmdResume(); };
    cmdNextFinding = async (): Promise<void> => { await this._cmdNextFinding(); };
    cmdAcceptFinding = async (): Promise<void> => { await this._cmdAcceptFinding(); };
    cmdRejectFinding = async (): Promise<void> => { await this._cmdRejectFinding(); };
    cmdDiscuss = async (): Promise<void> => { await this._cmdDiscuss(); };
    cmdSelectFinding = async (index: number): Promise<void> => { await this._cmdSelectFinding(index); };
    cmdReviewFinding = async (): Promise<void> => { await this._cmdReviewFinding(); };
    cmdClearSession = async (): Promise<void> => { await this._cmdClearSession(); };
    cmdRerunAnalysis = async (): Promise<void> => { await this._cmdRerunAnalysis(); };
    cmdSelectModel = async (): Promise<void> => { await this._cmdSelectModel(); };
    cmdStopServer = (): void => { this._cmdStopServer(); };
    cmdRefreshSessions = async (): Promise<void> => { await this._cmdRefreshSessions(); };
    cmdViewSession = async (item: any): Promise<void> => { await this._cmdViewSession(item); };
    cmdDeleteSession = async (item?: any): Promise<void> => { await this._cmdDeleteSession(item); };
    cmdRefreshLearning = async (): Promise<void> => { await this._cmdRefreshLearning(); };
    cmdExportLearning = async (): Promise<void> => { await this._cmdExportLearning(); };
    cmdResetLearning = async (): Promise<void> => { await this._cmdResetLearning(); };
    cmdDeleteLearningEntry = async (item: any): Promise<void> => { await this._cmdDeleteLearningEntry(item); };

    // Exposed for discussion-panel action dispatch
    handleFindingAction = async (action: string, data?: unknown): Promise<void> => {
        await this._handleFindingAction(action, data);
    };

    // Exposed for discussion-panel result callback
    handleDiscussionResult = async (result: DiscussResponse): Promise<void> => {
        await this._handleDiscussionResult(result);
    };

    // -----------------------------------------------------------------------
    // Private — analyze
    // -----------------------------------------------------------------------

    private async _cmdAnalyze(): Promise<void> {
        try {
            this.deps.state.closedSessionNotice = undefined;
            this.deps.state.indexChangeDismissed = false;
            await this.deps.ensureServer();
            const client = this.deps.getApiClient();

            const projectPath = this.deps.detectProjectPath();
            if (!projectPath) {
                void this.deps.ui.showErrorMessage(
                    'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                );
                return;
            }

            const existingSession = await client.checkSession(projectPath);
            const entryAction = await this._chooseAnalyzeEntryAction(client, projectPath, existingSession);
            if (!entryAction) {
                return;
            }

            if (entryAction.kind === 'resume-default') {
                return this._cmdResume();
            }

            if (entryAction.kind === 'resume-by-id') {
                this.deps.presenter.setAnalyzing('Resuming session...');
                const summary = await this._resumeSessionByIdWithScenePathRecovery(
                    client, projectPath, entryAction.sessionId,
                );

                if (summary.error) {
                    this.deps.presenter.setError(summary.error);
                    void this.deps.ui.showErrorMessage(`lit-critic: Resume failed — ${summary.error}`);
                    return;
                }

                await this._openSessionSceneFiles(summary.scene_paths ?? [summary.scene_path]);

                void this.deps.ui.showInformationMessage(
                    `lit-critic: Resumed session — ${summary.total_findings} findings, ` +
                    `continuing from #${summary.current_index + 1}`
                );

                await this._populateFindingsAfterAnalysis(summary);
                await this.deps.sessionsTreeProvider.refresh();
                this.deps.sessionsTreeProvider.setCurrentSession(entryAction.sessionId);
                this.deps.presenter.revealCurrentSessionSelection();
                this._handleIndexChangeReport(summary.index_change ?? null);

                const finding = await client.getCurrentFinding();
                this._handleIndexChangeReport(finding.index_change ?? null);
                this._presentFinding(finding, summary.current_index);
                this._refreshManagementViews();
                return;
            }

            // start-new: show picker
            const resolved = await this._resolveSceneFiles();
            if (!resolved) {
                void this.deps.ui.showErrorMessage('lit-critic: No scene file selected.');
                return;
            }
            const scenePath = resolved.scenePaths[0];
            const scenePaths = resolved.scenePaths.length > 1 ? resolved.scenePaths : undefined;

            const config = this.deps.ui.getExtensionConfig();
            const model = getConfiguredAnalysisModel(config);
            const discussionModel = config.get<string>('discussionModel', '') || undefined;
            const lensPreset = config.get<string>('lensPreset', 'auto');
            let effectivePreset = lensPreset;
            if (lensPreset === 'auto') {
                effectivePreset = resolved.scenePaths.length > 1 ? 'multi-scene' : 'single-scene';
            }

            const serverConfig = await client.getConfig().catch(() => undefined);
            const selectedModel = serverConfig
                ? resolvePreferredModel(model, serverConfig)
                : model;
            this.deps.presenter.setAnalyzing(buildAnalysisStartStatusMessage(effectivePreset, serverConfig));
            void this.deps.ui.showInformationMessage('lit-critic: Starting analysis...');

            let firstProgressEventSeen = false;
            let resolveFirstProgressEvent: (() => void) | undefined;
            const firstProgressEventPromise = new Promise<void>((resolve) => {
                resolveFirstProgressEvent = resolve;
            });
            const markFirstProgressEvent = (): void => {
                if (firstProgressEventSeen) { return; }
                firstProgressEventSeen = true;
                resolveFirstProgressEvent?.();
                resolveFirstProgressEvent = undefined;
            };

            const analysisPromise = (async () => {
                try {
                    return await client.analyze(
                        scenePath, projectPath, selectedModel, discussionModel,
                        undefined, { preset: effectivePreset }, scenePaths,
                    );
                } catch (err) {
                    const message = err instanceof Error ? err.message : String(err);
                    const detail = tryParseRepoPathInvalidDetail(message);
                    if (!detail) { throw err; }
                    const sm = this.deps.getServerManager();
                    const repoRoot = sm?.repoRoot;
                    if (!repoRoot) { throw err; }
                    await client.updateRepoPath(repoRoot);
                    return client.analyze(
                        scenePath, projectPath, selectedModel, discussionModel,
                        undefined, { preset: effectivePreset }, scenePaths,
                    );
                }
            })();

            await new Promise((r) => setTimeout(r, 250));

            const progressPromise = new Promise<void>((resolve) => {
                client.streamAnalysisProgress(
                    (event) => {
                        markFirstProgressEvent();
                        switch (event.type) {
                            case 'status':
                                this.deps.presenter.setAnalyzing(event.message);
                                break;
                            case 'lens_complete':
                                this.deps.presenter.setAnalyzing(`✓ ${event.lens} complete`);
                                break;
                            case 'lens_error':
                                void this.deps.ui.showErrorMessage(`lit-critic: ${event.lens} lens failed: ${event.message}`);
                                break;
                            case 'complete':
                                this.deps.presenter.setAnalyzing('Analysis complete!');
                                break;
                            case 'done':
                                markFirstProgressEvent();
                                resolve();
                                break;
                        }
                    },
                    () => { markFirstProgressEvent(); resolve(); },
                    () => { markFirstProgressEvent(); resolve(); },
                );
            });

            await this.deps.ui.withProgress(
                'lit-critic: Starting analysis',
                async (progress) => {
                    progress.report({ message: 'Sending analysis request...' });
                    await Promise.race([
                        firstProgressEventPromise,
                        analysisPromise.then(() => undefined),
                    ]);
                },
            );

            const summary = await analysisPromise;
            await progressPromise;

            if (summary.error) {
                this.deps.presenter.setError(summary.error);
                void this.deps.ui.showErrorMessage(`lit-critic: Analysis failed — ${summary.error}`);
                return;
            }

            let modelInfo = `Model: ${summary.model.label}`;
            if (summary.discussion_model) {
                modelInfo += ` · Discussion: ${summary.discussion_model.label}`;
            }

            void this.deps.ui.showInformationMessage(
                `lit-critic: Found ${summary.total_findings} findings ` +
                `(${summary.counts.critical} critical, ${summary.counts.major} major, ${summary.counts.minor} minor) · ${modelInfo}`
            );

            await this._populateFindingsAfterAnalysis(summary);

            const firstFinding = await client.getCurrentFinding();
            this._handleIndexChangeReport(firstFinding.index_change ?? null);
            this._presentFinding(firstFinding);
            this._refreshManagementViews();

        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.deps.presenter.setError(msg);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    // -----------------------------------------------------------------------
    // Private — resume
    // -----------------------------------------------------------------------

    private async _cmdResume(): Promise<void> {
        try {
            this.deps.state.closedSessionNotice = undefined;
            this.deps.state.indexChangeDismissed = false;
            await this.deps.runTrackedOperation(
                { id: 'resume-session', title: 'Resuming session', statusMessage: 'Resuming session...' },
                async () => {
                    await this.deps.ensureServer();
                    const client = this.deps.getApiClient();

                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) {
                        void this.deps.ui.showErrorMessage(
                            'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                        );
                        return;
                    }

                    this.deps.presenter.setAnalyzing('Resuming session...');
                    const summary = await this._resumeWithScenePathRecovery(client, projectPath);

                    if (summary.error) {
                        this.deps.presenter.setError(summary.error);
                        void this.deps.ui.showErrorMessage(`lit-critic: Resume failed — ${summary.error}`);
                        return;
                    }

                    await this._openSessionSceneFiles(summary.scene_paths ?? [summary.scene_path]);

                    void this.deps.ui.showInformationMessage(
                        `lit-critic: Resumed session — ${summary.total_findings} findings, ` +
                        `continuing from #${summary.current_index + 1}`
                    );

                    await this._populateFindingsAfterAnalysis(summary);
                    await this.deps.sessionsTreeProvider.refresh();
                    this.deps.sessionsTreeProvider.setCurrentSessionByScenePath(summary.scene_path);
                    this.deps.presenter.revealCurrentSessionSelection();
                    this._handleIndexChangeReport(summary.index_change ?? null);

                    const finding = await client.getCurrentFinding();
                    this._handleIndexChangeReport(finding.index_change ?? null);
                    this._presentFinding(finding);
                    this._refreshManagementViews();
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.deps.presenter.setError(msg);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    // -----------------------------------------------------------------------
    // Private — finding navigation
    // -----------------------------------------------------------------------

    private async _cmdNextFinding(): Promise<void> {
        try {
            const client = this.deps.getApiClient();
            const resp = await client.continueFinding();
            if (!resp.complete && resp.finding) {
                this._updateCachedFinding(resp.finding);
            }
            this._handleAdvanceResponse(resp);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdAcceptFinding(): Promise<void> {
        try {
            const client = this.deps.getApiClient();
            const resp = await client.acceptFinding();
            const next = resp.next ?? resp;

            if (this.deps.state.allFindings[this.deps.state.currentFindingIndex]) {
                this.deps.state.allFindings[this.deps.state.currentFindingIndex].status = 'accepted';
                this.deps.diagnosticsProvider.removeFinding(
                    this.deps.state.allFindings[this.deps.state.currentFindingIndex].number,
                );
                this.deps.findingsTreeProvider.updateFinding(
                    this.deps.state.allFindings[this.deps.state.currentFindingIndex],
                );
            }

            if (!next.complete && next.finding) {
                this._updateCachedFinding(next.finding);
            }

            this._handleAdvanceResponse(next);
            await this.deps.sessionsTreeProvider.refresh();
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdRejectFinding(): Promise<void> {
        try {
            const reason = await this.deps.ui.showInputBox({
                prompt: 'Reason for rejecting this finding (optional)',
                placeHolder: 'e.g., This is intentional for voice consistency',
            });

            const client = this.deps.getApiClient();
            const resp = await client.rejectFinding(reason || '');
            const next = resp.next ?? resp;

            if (this.deps.state.allFindings[this.deps.state.currentFindingIndex]) {
                this.deps.state.allFindings[this.deps.state.currentFindingIndex].status = 'rejected';
                this.deps.diagnosticsProvider.removeFinding(
                    this.deps.state.allFindings[this.deps.state.currentFindingIndex].number,
                );
                this.deps.findingsTreeProvider.updateFinding(
                    this.deps.state.allFindings[this.deps.state.currentFindingIndex],
                );
            }

            if (!next.complete && next.finding) {
                this._updateCachedFinding(next.finding);
            }

            this._handleAdvanceResponse(next);
            await this.deps.sessionsTreeProvider.refresh();
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdDiscuss(): Promise<void> {
        this.deps.ensureDiscussionPanel();
        const client = this.deps.getApiClient();

        try {
            const finding = await client.getCurrentFinding();
            this._handleIndexChangeReport(finding.index_change ?? null);
            if (!finding.complete && finding.finding) {
                this._updateCachedFinding(finding.finding);
                this.deps.ensureDiscussionPanel().show(
                    finding.finding,
                    finding.current ?? 1,
                    finding.total ?? this.deps.state.totalFindings,
                    finding.is_ambiguity ?? false,
                );
            }
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdSelectFinding(index: number): Promise<void> {
        try {
            const client = this.deps.getApiClient();
            this.deps.state.currentFindingIndex = index;
            this.deps.findingsTreeProvider.setCurrentIndex(this.deps.state.currentFindingIndex);
            this.deps.presenter.revealCurrentFindingSelection();

            let resp: AdvanceResponse;
            try {
                resp = await client.gotoFinding(index);
            } catch (gotoErr) {
                const cached = this.deps.state.allFindings[index];
                if (!cached) { throw gotoErr; }

                await this.deps.ui.navigateToFindingLine(cached);
                this.deps.ensureDiscussionPanel().show(
                    cached,
                    index + 1,
                    getSafeTotalFindings(this.deps.state.totalFindings, this.deps.state.allFindings),
                    cached.ambiguity_type !== null,
                    undefined,
                    this.deps.state.closedSessionNotice,
                );
                return;
            }

            if (!resp.complete && resp.finding) {
                this._updateCachedFinding(resp.finding);
                await this.deps.ui.navigateToFindingLine(resp.finding);
            }

            this._handleAdvanceResponse(resp, index);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdReviewFinding(): Promise<void> {
        try {
            const client = this.deps.getApiClient();
            const resp = await client.reviewFinding();
            this._handleIndexChangeReport(resp.index_change ?? null);
            let discussionTransition: DiscussionContextTransition | undefined;

            if (!resp.complete && resp.finding) {
                const previousFinding = this.deps.state.allFindings[this.deps.state.currentFindingIndex];
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

                this._updateCachedFinding(resp.finding);
            }

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
                            void this.deps.ui.showErrorMessage(
                                'lit-critic: Review reported completion but pending findings remain. Restored current finding.'
                            );
                            this._presentFinding(fallback);
                            return;
                        }
                    }
                } catch {
                    // Non-fatal consistency check
                }
            }

            this._presentFinding(resp, undefined, discussionTransition);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdClearSession(): Promise<void> {
        try {
            const confirm = await this.deps.ui.showWarningMessage(
                'Delete saved session?', true, 'Delete',
            );
            if (confirm !== 'Delete') {
                return;
            }

            const client = this.deps.getApiClient();
            await client.clearSession();
            void this.deps.ui.showInformationMessage('lit-critic: Session cleared.');

            this.deps.diagnosticsProvider.clear();
            this.deps.findingsTreeProvider.clear();
            this.deps.presenter.setReady();
            this.deps.state.allFindings = [];
            this.deps.state.closedSessionNotice = undefined;
            this.deps.state.indexChangeDismissed = false;
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdRerunAnalysis(): Promise<void> {
        try {
            await this.deps.ensureServer();
            const client = this.deps.getApiClient();

            const projectPath = this.deps.detectProjectPath();
            if (!projectPath) {
                void this.deps.ui.showErrorMessage(
                    'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                );
                return;
            }

            this.deps.presenter.setAnalyzing('Re-running analysis with updated indexes...');
            const summary = await client.rerunAnalysis(projectPath);

            if (summary.error) {
                this.deps.presenter.setError(summary.error);
                void this.deps.ui.showErrorMessage(`lit-critic: Re-run failed — ${summary.error}`);
                return;
            }

            this.deps.state.indexChangeDismissed = false;
            this.deps.presenter.closeDiscussion();

            await this._populateFindingsAfterAnalysis(summary);
            const firstFinding = await client.getCurrentFinding();
            this._presentFinding(firstFinding);
            this._refreshManagementViews();

            void this.deps.ui.showInformationMessage('lit-critic: Analysis re-run completed with updated indexes.');
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.deps.presenter.setError(msg);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdSelectModel(): Promise<void> {
        try {
            await this.deps.ensureServer();
            const client = this.deps.getApiClient();
            const config = await client.getConfig();
            const extConfig = this.deps.ui.getExtensionConfig();
            const configuredModel = getConfiguredAnalysisModel(extConfig);
            const resolvedCurrentModel = resolvePreferredModel(configuredModel, config);

            const items = Object.entries(config.available_models).map(([name, info]) => ({
                label: name,
                description: info.label,
                detail: name === resolvedCurrentModel ? 'Current model' : undefined,
            }));

            const selected = await this.deps.ui.showQuickPick(items, {
                placeHolder: 'Select a model for analysis',
                activeItemLabel: resolvedCurrentModel,
            });

            if (selected) {
                const label = typeof selected === 'string' ? selected : selected.label;
                const writableConfig = extConfig as any;
                if (typeof writableConfig.update === 'function') {
                    await writableConfig.update('analysisModel', label, 2 /* Workspace */);
                }
                void this.deps.ui.showInformationMessage(`lit-critic: Model set to ${label}`);
            }
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private _cmdStopServer(): void {
        const sm = this.deps.getServerManager();
        if (sm) {
            sm.stop();
            this.deps.presenter.setReady();
            void this.deps.ui.showInformationMessage('lit-critic: Server stopped.');
        } else {
            void this.deps.ui.showInformationMessage('lit-critic: No server is running.');
        }
    }

    // -----------------------------------------------------------------------
    // Private — management commands
    // -----------------------------------------------------------------------

    private async _cmdRefreshSessions(): Promise<void> {
        try {
            await this.deps.runTrackedOperation(
                { id: 'refresh-sessions', title: 'Refreshing sessions', statusMessage: 'Refreshing sessions...' },
                async () => {
                    await this.deps.ensureServer();
                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) {
                        void this.deps.ui.showErrorMessage(
                            'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                        );
                        return;
                    }
                    const client = this.deps.getApiClient();
                    this.deps.sessionsTreeProvider.setApiClient(client);
                    this.deps.sessionsTreeProvider.setProjectPath(projectPath);
                    await this.deps.sessionsTreeProvider.refresh();
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdViewSession(item: any): Promise<void> {
        try {
            await this.deps.runTrackedOperation(
                { id: 'view-session', title: 'Loading session findings', statusMessage: 'Loading session findings...' },
                async () => {
                    await this.deps.ensureServer();
                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) {
                        void this.deps.ui.showErrorMessage('lit-critic: Could not detect project directory.');
                        return;
                    }

                    const sessionId = typeof item === 'number' ? item : item?.session?.id;
                    if (!sessionId) {
                        void this.deps.ui.showErrorMessage('lit-critic: Could not determine session ID.');
                        return;
                    }

                    const client = this.deps.getApiClient();
                    const detail = await client.getSessionDetail(sessionId, projectPath);

                    if (detail.status === 'active') {
                        this.deps.state.closedSessionNotice = undefined;
                        this.deps.state.indexChangeDismissed = false;
                        this.deps.presenter.setAnalyzing('Resuming session...');
                        this.deps.ui.setStatusBarMessage(
                            `lit-critic: Switching to ${path.basename(detail.scene_path)}...`, 2500,
                        );

                        const summary = await this._resumeSessionByIdWithScenePathRecovery(client, projectPath, sessionId);

                        if (summary.error) {
                            this.deps.presenter.setError(summary.error);
                            void this.deps.ui.showErrorMessage(`lit-critic: Resume failed — ${summary.error}`);
                            return;
                        }

                        await this._openSessionSceneFiles(
                            summary.scene_paths && summary.scene_paths.length > 0
                                ? summary.scene_paths
                                : [summary.scene_path || detail.scene_path],
                        );

                        await this._populateFindingsAfterAnalysis(summary);
                        await this.deps.sessionsTreeProvider.refresh();
                        this.deps.sessionsTreeProvider.setCurrentSession(sessionId);
                        this.deps.presenter.revealCurrentSessionSelection();
                        this._handleIndexChangeReport(summary.index_change ?? null);

                        const currentFinding = await client.getCurrentFinding();
                        this._handleIndexChangeReport(currentFinding.index_change ?? null);
                        if (!currentFinding.complete && currentFinding.finding) {
                            this._updateCachedFinding(currentFinding.finding);
                        }
                        this._presentFinding(currentFinding, summary.current_index);
                        this.deps.presenter.setProgress(summary.current_index + 1, summary.total_findings);

                        void this.deps.ui.showInformationMessage(
                            `lit-critic: Resumed session — ${summary.total_findings} findings, ` +
                            `continuing from #${summary.current_index + 1}`
                        );

                    } else {
                        this.deps.presenter.setAnalyzing('Loading session...');
                        const summary = await this._viewSessionByIdWithScenePathRecovery(client, projectPath, sessionId);

                        if (summary.error) {
                            this.deps.presenter.setError(summary.error);
                            void this.deps.ui.showErrorMessage(`lit-critic: Load failed — ${summary.error}`);
                            return;
                        }

                        this.deps.state.closedSessionNotice = `Viewing ${detail.status} session — actions will reopen it.`;

                        await this._openSessionSceneFiles(
                            summary.scene_paths && summary.scene_paths.length > 0
                                ? summary.scene_paths
                                : [summary.scene_path || detail.scene_path],
                        );

                        await this._populateFindingsAfterAnalysis(summary);
                        await this.deps.sessionsTreeProvider.refresh();
                        this.deps.sessionsTreeProvider.setCurrentSession(sessionId);
                        this.deps.presenter.revealCurrentSessionSelection();
                        this._handleIndexChangeReport(summary.index_change ?? null);

                        const currentFinding = await client.getCurrentFinding();
                        this._handleIndexChangeReport(currentFinding.index_change ?? null);
                        if (!currentFinding.complete && currentFinding.finding) {
                            this._updateCachedFinding(currentFinding.finding);
                        }

                        const selectedIndex = Math.min(
                            Math.max(detail.current_index ?? 0, 0),
                            Math.max(0, summary.total_findings - 1),
                        );

                        this._presentFinding(currentFinding, selectedIndex);
                        this.deps.presenter.setProgress(selectedIndex + 1, summary.total_findings);

                        void this.deps.ui.showInformationMessage(
                            `Viewing ${detail.status} session: ${summary.total_findings} findings`
                        );

                        this._refreshManagementViews();
                    }
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdDeleteSession(item?: any): Promise<void> {
        try {
            await this.deps.runTrackedOperation(
                { id: 'delete-session', title: 'Deleting session', statusMessage: 'Deleting session...' },
                async () => {
                    const sessionId = typeof item === 'number' ? item : item?.session?.id;

                    if (!sessionId) {
                        void this.deps.ui.showErrorMessage(
                            'lit-critic: Select a session in the Sessions view to delete.'
                        );
                        return;
                    }

                    const confirm = await this.deps.ui.showWarningMessage(
                        `Delete session #${sessionId}? This cannot be undone.`, true, 'Delete',
                    );
                    if (confirm !== 'Delete') {
                        return;
                    }

                    await this.deps.ensureServer();
                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) { return; }

                    const client = this.deps.getApiClient();
                    const sessionInfo = await client.getSession();
                    const isActiveSession = sessionInfo.active && item?.session?.status === 'active';

                    await client.deleteSession(sessionId, projectPath);
                    void this.deps.ui.showInformationMessage(`lit-critic: Session #${sessionId} deleted.`);

                    if (isActiveSession) {
                        this.deps.diagnosticsProvider.clear();
                        this.deps.findingsTreeProvider.clear();
                        this.deps.presenter.setReady();
                        this.deps.state.allFindings = [];
                        this.deps.state.currentFindingIndex = 0;
                        this.deps.state.totalFindings = 0;
                        this.deps.getDiscussionPanel()?.close();
                        this.deps.sessionsTreeProvider.setCurrentSession(null);
                    }

                    await this.deps.sessionsTreeProvider.refresh();
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdRefreshLearning(): Promise<void> {
        try {
            await this.deps.runTrackedOperation(
                { id: 'refresh-learning', title: 'Refreshing learning data', statusMessage: 'Refreshing learning data...' },
                async () => {
                    await this.deps.ensureServer();
                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) {
                        void this.deps.ui.showErrorMessage(
                            'lit-critic: Could not detect project directory (no CANON.md found in workspace).'
                        );
                        return;
                    }
                    const client = this.deps.getApiClient();
                    this.deps.learningTreeProvider.setApiClient(client);
                    this.deps.learningTreeProvider.setProjectPath(projectPath);
                    await this.deps.learningTreeProvider.refresh();
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdExportLearning(): Promise<void> {
        try {
            await this.deps.runTrackedOperation(
                { id: 'export-learning', title: 'Exporting learning data', statusMessage: 'Exporting learning data...' },
                async () => {
                    await this.deps.ensureServer();
                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) { return; }
                    const client = this.deps.getApiClient();
                    const result = await client.exportLearning(projectPath);
                    void this.deps.ui.showInformationMessage(`lit-critic: LEARNING.md exported to ${result.path}`);
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.deps.presenter.setError(msg);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdResetLearning(): Promise<void> {
        try {
            await this.deps.runTrackedOperation(
                { id: 'reset-learning', title: 'Resetting learning data', statusMessage: 'Resetting learning data...' },
                async () => {
                    const confirm = await this.deps.ui.showWarningMessage(
                        'Reset all learning data? This will delete all preferences, blind spots, and resolutions. This cannot be undone.',
                        true, 'Reset',
                    );
                    if (confirm !== 'Reset') { return; }

                    await this.deps.ensureServer();
                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) { return; }

                    await this.deps.getApiClient().resetLearning(projectPath);
                    void this.deps.ui.showInformationMessage('lit-critic: Learning data reset.');
                    await this.deps.learningTreeProvider.refresh();
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.deps.presenter.setError(msg);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    private async _cmdDeleteLearningEntry(item: any): Promise<void> {
        try {
            await this.deps.runTrackedOperation(
                { id: 'delete-learning-entry', title: 'Deleting learning entry', statusMessage: 'Deleting learning entry...' },
                async () => {
                    const entryId = typeof item === 'number'
                        ? item
                        : (item?.entryId ?? item?.entry?.id);

                    if (!entryId) {
                        void this.deps.ui.showErrorMessage('lit-critic: Could not determine learning entry ID.');
                        return;
                    }

                    await this.deps.ensureServer();
                    const projectPath = this.deps.detectProjectPath();
                    if (!projectPath) { return; }

                    await this.deps.getApiClient().deleteLearningEntry(entryId, projectPath);
                    void this.deps.ui.showInformationMessage('lit-critic: Learning entry deleted.');
                    await this.deps.learningTreeProvider.refresh();
                },
            );
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
        }
    }

    // -----------------------------------------------------------------------
    // Private — action dispatch
    // -----------------------------------------------------------------------

    private async _handleFindingAction(action: string, data?: unknown): Promise<void> {
        switch (action) {
            case 'accept':
                await this._cmdAcceptFinding();
                break;
            case 'reject':
                await this._cmdRejectFinding();
                break;
            case 'continue':
                await this._cmdNextFinding();
                break;
            case 'reviewFinding':
                await this._cmdReviewFinding();
                break;
            case 'ambiguity':
                try {
                    await this.deps.getApiClient().markAmbiguity(data as boolean);
                    void this.deps.ui.showInformationMessage(
                        `lit-critic: Marked as ${data ? 'intentional' : 'accidental'}`
                    );
                } catch (err) {
                    const msg = err instanceof Error ? err.message : String(err);
                    void this.deps.ui.showErrorMessage(`lit-critic: ${msg}`);
                }
                break;
            case 'exportLearning':
                await this._cmdExportLearning();
                break;
            case 'rerunAnalysis':
                await this._cmdRerunAnalysis();
                break;
            case 'dismissIndexChange':
                this.deps.state.indexChangeDismissed = true;
                this.deps.ensureDiscussionPanel().clearIndexChangeNotice();
                break;
        }
    }

    // -----------------------------------------------------------------------
    // Private — helpers (stubs — filled in below)
    // -----------------------------------------------------------------------

    private _presentFinding(
        findingResp: FindingResponse,
        preferredIndex?: number,
        discussionTransition?: DiscussionContextTransition,
    ): void {
        const { state, presenter, deps } = { state: this.deps.state, presenter: this.deps.presenter, deps: this.deps };

        if (findingResp.complete) {
            presenter.setComplete();
            void deps.ui.showInformationMessage('lit-critic: All findings have been reviewed.');

            const fallback = resolveFallbackFinding(state.allFindings, state.currentFindingIndex, preferredIndex);
            if (fallback) {
                state.currentFindingIndex = fallback.index;
                deps.findingsTreeProvider.setCurrentIndex(state.currentFindingIndex);
                presenter.revealCurrentFindingSelection();

                const total = getSafeTotalFindings(state.totalFindings, state.allFindings);
                deps.ensureDiscussionPanel().show(
                    fallback.finding,
                    Math.min(total, state.currentFindingIndex + 1),
                    total,
                    fallback.finding.ambiguity_type !== null,
                    discussionTransition,
                );
            }
            return;
        }

        if (!findingResp.finding) {
            return;
        }

        state.currentFindingIndex = resolvePresentedFindingIndex(
            findingResp, state.allFindings, state.currentFindingIndex, preferredIndex,
        );
        state.totalFindings = findingResp.total ?? state.totalFindings;

        presenter.setProgress(findingResp.current ?? state.currentFindingIndex + 1, state.totalFindings);
        deps.findingsTreeProvider.setCurrentIndex(state.currentFindingIndex);
        presenter.revealCurrentFindingSelection();

        deps.ensureDiscussionPanel().show(
            findingResp.finding,
            findingResp.current ?? state.currentFindingIndex + 1,
            state.totalFindings,
            findingResp.is_ambiguity ?? false,
            discussionTransition,
            state.closedSessionNotice,
        );
    }

    private _handleAdvanceResponse(resp: AdvanceResponse, preferredIndex?: number): void {
        if (resp.scene_change) {
            const sc = resp.scene_change;
            void this.deps.ui.showInformationMessage(
                `📝 Scene change detected! Adjusted: ${sc.adjusted}, Stale: ${sc.stale}, Re-evaluated: ${sc.re_evaluated.length}`
            );
            this.deps.ensureDiscussionPanel().notifySceneChange(sc);
            void this._refreshDiagnosticsFromSession();
        }

        this._handleIndexChangeReport(resp.index_change ?? null);
        this._presentFinding(resp, preferredIndex);
    }

    private _handleIndexChangeReport(report: IndexChangeReport | null | undefined): void {
        if (!report || !report.stale) {
            this.deps.ensureDiscussionPanel().clearIndexChangeNotice();
            return;
        }

        if (report.prompt) {
            this.deps.state.indexChangeDismissed = false;
        }

        if (!this.deps.state.indexChangeDismissed) {
            this.deps.ensureDiscussionPanel().notifyIndexChange(report);
        }

        if (report.prompt) {
            const changed = report.changed_files?.length ? report.changed_files.join(', ') : 'index context';
            void this.deps.ui.showWarningMessage(
                `lit-critic: ${changed} changed. Findings may be stale. Re-run analysis is recommended.`,
                false,
                'Re-run Analysis',
                'Dismiss',
            ).then(async (choice) => {
                if (choice === 'Re-run Analysis') {
                    await this._cmdRerunAnalysis();
                } else if (choice === 'Dismiss') {
                    this.deps.state.indexChangeDismissed = true;
                    this.deps.ensureDiscussionPanel().clearIndexChangeNotice();
                }
            });
        }
    }

    private async _handleDiscussionResult(result: DiscussResponse): Promise<void> {
        if (result.error) {
            return;
        }

        this._handleIndexChangeReport(result.index_change ?? null);

        const activeFinding = this.deps.state.allFindings[this.deps.state.currentFindingIndex];
        if (!activeFinding) {
            return;
        }

        if (result.finding) {
            this._updateCachedFinding(result.finding);
        } else if (result.finding_status) {
            activeFinding.status = result.finding_status;
            this.deps.findingsTreeProvider.updateFinding(activeFinding);

            if (isTerminalFindingStatus(result.finding_status)) {
                this.deps.diagnosticsProvider.removeFinding(activeFinding.number);
            } else {
                this.deps.diagnosticsProvider.updateSingleFinding(activeFinding);
            }
        }

        const latestStatus = getLatestFindingStatus(result);
        if (latestStatus && latestStatus !== 'pending') {
            await this.deps.sessionsTreeProvider.refresh().catch(() => {});
            await this.deps.learningTreeProvider.refresh().catch(() => {});
        }
    }

    private async _populateFindingsAfterAnalysis(summary: AnalysisSummary): Promise<void> {
        const client = this.deps.getApiClient();

        let findingsStatus = summary.findings_status;

        if (!findingsStatus) {
            console.warn('lit-critic: findings_status not in analysis response, falling back to GET /api/session');
            try {
                const session = await client.getSession();
                if (!session.active || !session.findings_status) {
                    console.error('lit-critic: Failed to load findings from session endpoint');
                    void this.deps.ui.showErrorMessage('lit-critic: Could not load findings. Try resuming the session.');
                    return;
                }
                findingsStatus = session.findings_status;
            } catch (err) {
                const msg = err instanceof Error ? err.message : String(err);
                console.error('lit-critic: Error fetching session:', msg);
                void this.deps.ui.showErrorMessage(`lit-critic: Could not load findings — ${msg}`);
                return;
            }
        }

        this.deps.state.allFindings = findingsStatus.map((f) => ({
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

        this.deps.state.totalFindings = this.deps.state.allFindings.length;
        this.deps.findingsTreeProvider.setFindings(
            this.deps.state.allFindings, summary.scene_path, summary.current_index,
        );
        this.deps.presenter.revealCurrentFindingSelection();
        this.deps.diagnosticsProvider.setScenePath(summary.scene_path, summary.scene_paths);

        try {
            const firstFinding = await client.getCurrentFinding();
            if (!firstFinding.complete && firstFinding.finding) {
                this._updateCachedFinding(firstFinding.finding);
                this.deps.diagnosticsProvider.updateFromFindings(this.deps.state.allFindings);
            }
        } catch (err) {
            console.warn('lit-critic: Could not fetch first finding details:', err);
        }
    }

    private _updateCachedFinding(finding: Finding): void {
        const idx = this.deps.state.allFindings.findIndex((f) => f.number === finding.number);
        if (idx >= 0) {
            this.deps.state.allFindings[idx] = finding;
        } else {
            this.deps.state.allFindings.push(finding);
        }
        this.deps.findingsTreeProvider.updateFinding(finding);
        this.deps.diagnosticsProvider.updateFromFindings(this.deps.state.allFindings);
    }

    private async _refreshDiagnosticsFromSession(): Promise<void> {
        try {
            const session = await this.deps.getApiClient().getSession();
            if (session.active && session.findings_status) {
                this.deps.diagnosticsProvider.updateFromFindings(this.deps.state.allFindings);
            }
        } catch {
            // Non-critical
        }
    }

    private async _openSessionSceneFiles(scenePaths: Array<string | undefined>): Promise<void> {
        const candidates = scenePaths.filter((p): p is string => Boolean(p && p.trim()));
        if (candidates.length === 0) {
            return;
        }

        const deduped = Array.from(new Set(candidates));
        const existing = deduped.filter((p) => this.deps.ui.pathExists(p));
        if (existing.length === 0) {
            void this.deps.ui.showErrorMessage(`Scene file not found: ${deduped[0]}`);
            return;
        }

        const normalizePath = (p: string): string => path.normalize(p).toLowerCase();
        const openPaths = new Set(
            this.deps.ui.getOpenTextDocumentPaths().map(normalizePath),
        );
        const filesToOpen = existing.filter((p) => !openPaths.has(normalizePath(p)));

        if (filesToOpen.length === 0) {
            return;
        }

        await this.deps.ui.showTextDocument(filesToOpen[0], {
            viewColumn: 1,
            preview: false,
            preserveFocus: false,
        });

        for (let i = 1; i < filesToOpen.length; i++) {
            await this.deps.ui.showTextDocument(filesToOpen[i], {
                viewColumn: 1,
                preview: false,
                preserveFocus: true,
            });
        }
    }

    private _refreshManagementViews(): void {
        const projectPath = this.deps.detectProjectPath();
        const apiClient = this.deps.getApiClient();
        if (!projectPath || !apiClient) {
            return;
        }

        this.deps.sessionsTreeProvider.setApiClient(apiClient);
        this.deps.sessionsTreeProvider.setProjectPath(projectPath);
        this.deps.sessionsTreeProvider.refresh().catch(() => {});

        this.deps.learningTreeProvider.setApiClient(apiClient);
        this.deps.learningTreeProvider.setProjectPath(projectPath);
        this.deps.learningTreeProvider.refresh().catch(() => {});
    }
    private async _resumeWithScenePathRecovery(client: ApiClient, projectPath: string): Promise<AnalysisSummary> {
        return client.resumeWithRecovery(projectPath, undefined, this.deps.promptForScenePathOverride);
    }
    private async _resumeSessionByIdWithScenePathRecovery(
        client: ApiClient, projectPath: string, sessionId: number,
    ): Promise<AnalysisSummary> {
        return client.resumeSessionByIdWithRecovery(projectPath, sessionId, undefined, this.deps.promptForScenePathOverride);
    }
    private async _viewSessionByIdWithScenePathRecovery(
        client: ApiClient, projectPath: string, sessionId: number,
    ): Promise<AnalysisSummary> {
        return client.viewSessionWithRecovery(projectPath, sessionId, undefined, this.deps.promptForScenePathOverride);
    }
    private async _chooseAnalyzeEntryAction(
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
            // Non-fatal fallback
        }

        if (activeSessions.length > 1) {
            const items: Array<{ label: string; description?: string; detail?: string; action: AnalyzeEntryAction }> = [
                ...activeSessions.map((session) => ({
                    label: `Resume ${formatSessionLabel(session)}`,
                    description: `Created ${session.created_at}`,
                    detail: session.scene_path,
                    action: { kind: 'resume-by-id' as const, sessionId: session.id },
                })),
                {
                    label: 'Start new analysis',
                    detail: 'Create a fresh session for the current scene.',
                    action: { kind: 'start-new' as const },
                },
            ];

            const selected = await this.deps.ui.showQuickPick(items, {
                placeHolder: 'Multiple active sessions found. Choose one to resume, or start a new analysis.',
            });

            return selected?.action ?? null;
        }

        if (activeSessions.length === 1) {
            const active = activeSessions[0];
            const choice = await this.deps.ui.showQuickPick(
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

            return (typeof choice === 'string' ? choice : choice.label).startsWith('Resume ')
                ? { kind: 'resume-by-id', sessionId: active.id }
                : { kind: 'start-new' };
        }

        const sceneHint = existingSession.scene_path ? ` for ${path.basename(existingSession.scene_path)}` : '';
        const choice = await this.deps.ui.showQuickPick(
            ['Resume existing session', 'Start new analysis'],
            { placeHolder: `Found saved session${sceneHint}. Resume or start fresh?` },
        );

        if (!choice) {
            return null;
        }

        const choiceLabel = typeof choice === 'string' ? choice : choice.label;
        if (choiceLabel === 'Resume existing session') {
            if (typeof existingSession.session_id === 'number') {
                return { kind: 'resume-by-id', sessionId: existingSession.session_id };
            }
            return { kind: 'resume-default' };
        }

        return { kind: 'start-new' };
    }

    private async _resolveSceneFiles(): Promise<{ editor: any; scenePaths: string[] } | undefined> {
        const selected = await this.deps.ui.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: true,
            openLabel: 'Analyze Scene',
            title: 'Select scene file(s) to analyze',
        });

        if (!selected || selected.length === 0) {
            return undefined;
        }

        const allPaths = selected.map((u) => u.fsPath);

        try {
            const firstEditor = await this.deps.ui.showTextDocument(selected[0].fsPath, {
                preview: false,
                preserveFocus: false,
            });

            for (let i = 1; i < selected.length; i++) {
                await this.deps.ui.showTextDocument(selected[i].fsPath, {
                    preview: false,
                    preserveFocus: true,
                });
            }

            return { editor: firstEditor, scenePaths: allPaths };
        } catch {
            return undefined;
        }
    }
}
