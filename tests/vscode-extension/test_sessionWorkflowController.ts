/**
 * Tests for SessionWorkflowController.
 *
 * Uses a fake WorkflowDeps/WorkflowUiPort so that no real VS Code runtime,
 * ServerManager, or ApiClient is loaded.
 */

import { strict as assert } from 'assert';

import {
    SessionWorkflowController,
    WorkflowDeps,
    WorkflowUiPort,
} from '../../vscode-extension/src/workflows/sessionWorkflowController';
import { createRuntimeStateStore } from '../../vscode-extension/src/workflows/stateStore';

// ---------------------------------------------------------------------------
// Minimal fakes
// ---------------------------------------------------------------------------

type Call = { method: string; args?: any[] };

function makeApiClient(overrides: Record<string, (...args: any[]) => any> = {}): any {
    return {
        checkSession: async (_pp: string) => ({ exists: false }),
        listSessions: async () => ({ sessions: [] }),
        resumeWithRecovery: async () => ({ error: null, total_findings: 3, current_index: 0, scene_path: '/f.md', findings_status: [], counts: { critical: 0, major: 0, minor: 0 }, model: { label: 'gpt' } }),
        resumeSessionByIdWithRecovery: async () => ({ error: null, total_findings: 2, current_index: 0, scene_path: '/f.md', findings_status: [], counts: {}, model: { label: 'm' } }),
        continueFinding: async () => ({ complete: false, finding: null, current: 2, total: 3 }),
        acceptFinding: async () => ({ next: { complete: false, finding: null, current: 2, total: 3 } }),
        rejectFinding: async () => ({ next: { complete: false, finding: null, current: 2, total: 3 } }),
        getCurrentFinding: async () => ({ complete: false, finding: null, current: 1, total: 3 }),
        getSession: async () => ({ active: false, findings_status: [] }),
        clearSession: async () => ({}),
        getConfig: async () => ({ available_models: {}, default_model: 'x' }),
        rerunAnalysis: async (_pp: string) => ({ error: null, total_findings: 3, current_index: 0, scene_path: '/f.md', findings_status: [], counts: {}, model: { label: 'm' } }),
        exportLearning: async () => ({ path: '/out/LEARNING.md' }),
        resetLearning: async () => ({}),
        deleteLearningEntry: async () => ({}),
        deleteSession: async () => ({}),
        getSessionDetail: async () => ({ id: 1, status: 'active', scene_path: '/f.md', current_index: 0 }),
        markAmbiguity: async () => ({}),
        gotoFinding: async () => ({ complete: false, finding: null }),
        reviewFinding: async () => ({ complete: false, finding: null }),
        updateRepoPath: async () => ({}),
        ...overrides,
    };
}

function makePresenter(): any {
    const calls: Call[] = [];
    return {
        _calls: calls,
        setAnalyzing: (m?: string) => calls.push({ method: 'setAnalyzing', args: [m] }),
        setReady: () => calls.push({ method: 'setReady' }),
        setError: (m: string) => calls.push({ method: 'setError', args: [m] }),
        setProgress: (c: number, t: number) => calls.push({ method: 'setProgress', args: [c, t] }),
        setComplete: () => calls.push({ method: 'setComplete' }),
        closeDiscussion: () => calls.push({ method: 'closeDiscussion' }),
        revealCurrentFindingSelection: () => {},
        revealCurrentSessionSelection: () => {},
    };
}

function makeDiscussionPanel(): any {
    const calls: Call[] = [];
    return {
        _calls: calls,
        show: (...args: any[]) => calls.push({ method: 'show', args }),
        close: () => calls.push({ method: 'close' }),
        notifySceneChange: (r: any) => calls.push({ method: 'notifySceneChange', args: [r] }),
        notifyIndexChange: (r: any) => calls.push({ method: 'notifyIndexChange', args: [r] }),
        clearIndexChangeNotice: () => calls.push({ method: 'clearIndexChangeNotice' }),
        onFindingAction: null,
        onDiscussionResult: null,
    };
}

function makeFindingsTreeProvider(): any {
    return {
        setFindings: () => {},
        setCurrentIndex: () => {},
        updateFinding: () => {},
        clear: () => {},
        getCurrentFindingItem: () => undefined,
    };
}

function makeSessionsTreeProvider(): any {
    return {
        setApiClient: () => {},
        setProjectPath: () => {},
        refresh: async () => {},
        setCurrentSession: () => {},
        setCurrentSessionByScenePath: () => {},
        getCurrentSessionItem: () => undefined,
    };
}

function makeLearningTreeProvider(): any {
    return {
        setApiClient: () => {},
        setProjectPath: () => {},
        refresh: async () => {},
    };
}

function makeDiagnosticsProvider(): any {
    return {
        setScenePath: () => {},
        updateFromFindings: () => {},
        updateSingleFinding: () => {},
        removeFinding: () => {},
        clear: () => {},
        scenePath: null,
    };
}

function makeUiPort(overrides: Partial<WorkflowUiPort> = {}): WorkflowUiPort {
    const messages: string[] = [];
    return {
        _messages: messages,
        showInformationMessage: async (m: string) => { messages.push(`info:${m}`); return undefined; },
        showErrorMessage: async (m: string) => { messages.push(`error:${m}`); return undefined; },
        showWarningMessage: async (m: string, _modal: boolean, ...items: string[]) => {
            messages.push(`warn:${m}`);
            return undefined;
        },
        showInputBox: async () => undefined,
        showQuickPick: async () => undefined,
        showOpenDialog: async () => undefined,
        showTextDocument: async () => undefined,
        withProgress: async (_title: string, task: any) => { await task({ report: () => {} }); },
        setStatusBarMessage: (_m: string, _t: number) => ({ dispose: () => {} }),
        navigateToFindingLine: async () => {},
        pathExists: () => false,
        getOpenTextDocumentPaths: () => [],
        getExtensionConfig: () => ({
            get: (key: string, def: any) => def,
            inspect: () => undefined,
        }),
        ...overrides,
    } as any;
}

function makeDeps(overrides: {
    apiClient?: any;
    presenter?: any;
    discussionPanel?: any;
    ui?: Partial<WorkflowUiPort>;
    stateOverrides?: any;
    ensureServerError?: Error;
    detectProjectPath?: () => string | undefined;
} = {}): WorkflowDeps {
    const apiClient = overrides.apiClient ?? makeApiClient();
    const panel = overrides.discussionPanel ?? makeDiscussionPanel();
    const state = createRuntimeStateStore();
    Object.assign(state, overrides.stateOverrides ?? {});

    return {
        getApiClient: () => apiClient,
        ensureServer: async () => {
            if (overrides.ensureServerError) { throw overrides.ensureServerError; }
        },
        getServerManager: () => undefined,
        state,
        presenter: overrides.presenter ?? makePresenter(),
        findingsTreeProvider: makeFindingsTreeProvider(),
        sessionsTreeProvider: makeSessionsTreeProvider(),
        learningTreeProvider: makeLearningTreeProvider(),
        diagnosticsProvider: makeDiagnosticsProvider(),
        ensureDiscussionPanel: () => panel,
        getDiscussionPanel: () => panel,
        runTrackedOperation: async (_profile, op) => op(),
        detectProjectPath: overrides.detectProjectPath ?? (() => '/project'),
        promptForScenePathOverride: async () => undefined,
        ui: makeUiPort(overrides.ui),
    };
}

// ---------------------------------------------------------------------------
// cmdAnalyze — start-new path
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdAnalyze', () => {
    it('shows error when no project path detected', async () => {
        const deps = makeDeps({ detectProjectPath: () => undefined });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdAnalyze();

        assert.ok(messages.some(m => m.includes('Could not detect project')));
    });

    it('resumes selected active session by id when user picks Resume', async () => {
        let resumeByIdCalled = false;
        const api = makeApiClient({
            checkSession: async () => ({ exists: true, session_id: undefined }),
            listSessions: async () => ({ sessions: [{ id: 1, status: 'active', scene_path: '/s.md', created_at: 't' }] }),
            resumeSessionByIdWithRecovery: async () => {
                resumeByIdCalled = true;
                return { error: null, total_findings: 1, current_index: 0, scene_path: '/s.md', findings_status: [], counts: {}, model: { label: 'm' } };
            },
        });
        const ui = makeUiPort({
            showQuickPick: async (items: any[]) => {
                // User picks 'Resume' option
                return items.find(i => (typeof i === 'string' ? i : i.label ?? i).toString().startsWith('Resume'));
            },
        });
        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAnalyze();

        assert.ok(resumeByIdCalled, 'should have called resumeSessionByIdWithRecovery');
    });

    it('shows file picker when user picks start-new', async () => {
        let pickerCalled = false;
        const api = makeApiClient({
            checkSession: async () => ({ exists: false }),
        });
        const ui = makeUiPort({
            showOpenDialog: async () => { pickerCalled = true; return undefined; },
        });
        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAnalyze();

        assert.ok(pickerCalled, 'open dialog should be called for start-new');
    });

    it('shows error message when no scene file selected', async () => {
        const api = makeApiClient({ checkSession: async () => ({ exists: false }) });
        const ui = makeUiPort({ showOpenDialog: async () => undefined });
        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (ui as any)._messages;

        await ctrl.cmdAnalyze();

        assert.ok(messages.some(m => m.includes('No scene file selected')));
    });
});

// ---------------------------------------------------------------------------
// cmdResume
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdResume', () => {
    it('resets closedSessionNotice and indexChangeDismissed before resuming', async () => {
        const deps = makeDeps({ stateOverrides: { closedSessionNotice: 'old notice', indexChangeDismissed: true } });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdResume();

        assert.equal(deps.state.closedSessionNotice, undefined);
        assert.equal(deps.state.indexChangeDismissed, false);
    });

    it('shows error when no project path detected', async () => {
        const deps = makeDeps({ detectProjectPath: () => undefined });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdResume();

        assert.ok(messages.some(m => m.includes('Could not detect project')));
    });

    it('shows error message when resume returns error', async () => {
        const api = makeApiClient({
            resumeWithRecovery: async () => ({ error: 'No session found', total_findings: 0, current_index: 0, scene_path: '', findings_status: [], counts: {}, model: { label: 'm' } }),
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdResume();

        assert.ok(messages.some(m => m.includes('Resume failed')));
    });

    it('shows success info message on happy path', async () => {
        const deps = makeDeps();
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdResume();

        assert.ok(messages.some(m => m.includes('Resumed session')));
    });

    it('opens all resolved scene files for multi-scene resume', async () => {
        const opened: string[] = [];
        const api = makeApiClient({
            resumeWithRecovery: async () => ({
                error: null,
                total_findings: 2,
                current_index: 0,
                scene_path: '/scene-1.md',
                scene_paths: ['/scene-1.md', '/scene-2.md'],
                findings_status: [],
                counts: {},
                model: { label: 'm' },
            }),
        });
        const deps = makeDeps({
            apiClient: api,
            ui: {
                pathExists: (p: string) => p === '/scene-1.md' || p === '/scene-2.md',
                showTextDocument: async (fsPath: string) => {
                    opened.push(fsPath);
                    return undefined;
                },
            },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdResume();

        assert.deepEqual(opened, ['/scene-1.md', '/scene-2.md']);
    });

    it('opens only missing scene files when others are already open across groups', async () => {
        const opened: string[] = [];
        const api = makeApiClient({
            resumeWithRecovery: async () => ({
                error: null,
                total_findings: 3,
                current_index: 0,
                scene_path: '/scene-1.md',
                scene_paths: ['/scene-1.md', '/scene-2.md', '/scene-3.md'],
                findings_status: [],
                counts: {},
                model: { label: 'm' },
            }),
        });

        const deps = makeDeps({
            apiClient: api,
            ui: {
                pathExists: (p: string) =>
                    p === '/scene-1.md' || p === '/scene-2.md' || p === '/scene-3.md',
                getOpenTextDocumentPaths: () => ['/SCENE-1.md', '/scene-3.md'],
                showTextDocument: async (fsPath: string) => {
                    opened.push(fsPath);
                    return undefined;
                },
            },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdResume();

        assert.deepEqual(opened, ['/scene-2.md']);
    });
});

// ---------------------------------------------------------------------------
// cmdNextFinding / cmdAcceptFinding / cmdRejectFinding
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdNextFinding', () => {
    it('calls continueFinding on the api client', async () => {
        let called = false;
        const api = makeApiClient({ continueFinding: async () => { called = true; return { complete: true }; } });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdNextFinding();

        assert.ok(called, 'continueFinding should be called');
    });

    it('shows error message on API failure', async () => {
        const api = makeApiClient({ continueFinding: async () => { throw new Error('net error'); } });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdNextFinding();

        assert.ok(messages.some(m => m.includes('net error')));
    });
});

describe('SessionWorkflowController.cmdAcceptFinding', () => {
    it('marks current finding as accepted in state', async () => {
        const deps = makeDeps({
            stateOverrides: { allFindings: [{ number: 1, status: 'pending' }], currentFindingIndex: 0 },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAcceptFinding();

        assert.equal(deps.state.allFindings[0].status, 'accepted');
    });
});

describe('SessionWorkflowController.cmdRejectFinding', () => {
    it('marks current finding as rejected in state', async () => {
        const deps = makeDeps({
            stateOverrides: { allFindings: [{ number: 2, status: 'pending' }], currentFindingIndex: 0 },
            ui: { showInputBox: async () => 'intentional' },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdRejectFinding();

        assert.equal(deps.state.allFindings[0].status, 'rejected');
    });
});

// ---------------------------------------------------------------------------
// cmdClearSession
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdClearSession', () => {
    it('does not clear when user does not confirm', async () => {
        let clearCalled = false;
        const api = makeApiClient({ clearSession: async () => { clearCalled = true; } });
        const deps = makeDeps({
            apiClient: api,
            ui: { showWarningMessage: async () => undefined },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdClearSession();

        assert.ok(!clearCalled, 'clearSession should not be called when user cancels');
    });

    it('clears state and shows info message when user confirms', async () => {
        const deps = makeDeps({
            stateOverrides: { allFindings: [{ number: 1 }] },
            ui: { showWarningMessage: async () => 'Delete' },
        });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdClearSession();

        assert.equal(deps.state.allFindings.length, 0, 'allFindings should be cleared');
        assert.ok(messages.some(m => m.includes('cleared')));
    });
});

// ---------------------------------------------------------------------------
// cmdRerunAnalysis
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdRerunAnalysis', () => {
    it('shows no project error when detectProjectPath returns undefined', async () => {
        const deps = makeDeps({ detectProjectPath: () => undefined });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdRerunAnalysis();

        assert.ok(messages.some(m => m.includes('Could not detect project')));
    });

    it('resets indexChangeDismissed and closes discussion on success', async () => {
        const presenter = makePresenter();
        const deps = makeDeps({
            presenter,
            stateOverrides: { indexChangeDismissed: true },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdRerunAnalysis();

        assert.equal(deps.state.indexChangeDismissed, false);
        assert.ok(presenter._calls.some((c: Call) => c.method === 'closeDiscussion'));
    });

    it('shows error on rerun failure', async () => {
        const api = makeApiClient({ rerunAnalysis: async () => ({ error: 'oops', total_findings: 0, current_index: 0, scene_path: '', findings_status: [], counts: {}, model: { label: 'm' } }) });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdRerunAnalysis();

        assert.ok(messages.some(m => m.includes('Re-run failed')));
    });
});

// ---------------------------------------------------------------------------
// cmdSelectModel
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdSelectModel', () => {
    it('preselects the currently configured model in quick pick', async () => {
        const quickPickCalls: Array<{ items: any[]; options?: any }> = [];
        let updatedModel: string | undefined;

        const api = makeApiClient({
            getConfig: async () => ({
                available_models: {
                    sonnet: { label: 'Sonnet 4.5' },
                    opus: { label: 'Opus 4.6' },
                },
                default_model: 'opus',
            }),
        });

        const ui = makeUiPort({
            showQuickPick: async (items: any[], options?: any) => {
                quickPickCalls.push({ items, options });
                return items.find((i: any) => i.label === 'sonnet');
            },
            getExtensionConfig: () => ({
                inspect: (key: string) => key === 'analysisModel' ? { workspaceValue: 'sonnet' } : undefined,
                get: (key: string, def: any) => {
                    if (key === 'analysisModel') {
                        return 'sonnet';
                    }
                    return def;
                },
                update: async (key: string, value: string) => {
                    if (key === 'analysisModel') {
                        updatedModel = value;
                    }
                },
            } as any),
        });

        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdSelectModel();

        assert.equal(quickPickCalls.length, 1, 'Expected one quick pick invocation');
        assert.equal(quickPickCalls[0].options?.activeItemLabel, 'sonnet');
        assert.ok(
            quickPickCalls[0].items.some((item: any) => item.label === 'sonnet' && item.detail === 'Current model'),
            'Expected currently configured model to be marked as Current model',
        );
        assert.equal(updatedModel, 'sonnet');
    });
});

// ---------------------------------------------------------------------------
// cmdStopServer
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdStopServer', () => {
    it('shows "no server" message when serverManager is undefined', async () => {
        const deps = makeDeps();
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        ctrl.cmdStopServer();

        assert.ok(messages.some(m => m.includes('No server')));
    });

    it('calls stop() and sets ready when serverManager exists', async () => {
        let stopCalled = false;
        const presenter = makePresenter();
        const deps: WorkflowDeps = {
            ...makeDeps({ presenter }),
            getServerManager: () => ({ stop: () => { stopCalled = true; }, isRunning: true }),
        };
        const ctrl = new SessionWorkflowController(deps);

        ctrl.cmdStopServer();

        assert.ok(stopCalled);
        assert.ok(presenter._calls.some((c: Call) => c.method === 'setReady'));
    });
});

// ---------------------------------------------------------------------------
// cmdViewSession
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdViewSession', () => {
    it('opens all resolved scene files when viewing an active multi-scene session', async () => {
        const opened: string[] = [];
        const api = makeApiClient({
            getSessionDetail: async () => ({ id: 7, status: 'active', scene_path: '/scene-1.md', current_index: 0 }),
            resumeSessionByIdWithRecovery: async () => ({
                error: null,
                total_findings: 2,
                current_index: 0,
                scene_path: '/scene-1.md',
                scene_paths: ['/scene-1.md', '/scene-2.md'],
                findings_status: [],
                counts: {},
                model: { label: 'm' },
            }),
        });
        const deps = makeDeps({
            apiClient: api,
            ui: {
                pathExists: (p: string) => p === '/scene-1.md' || p === '/scene-2.md',
                showTextDocument: async (fsPath: string) => {
                    opened.push(fsPath);
                    return undefined;
                },
            },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdViewSession({ session: { id: 7 } });

        assert.deepEqual(opened, ['/scene-1.md', '/scene-2.md']);
    });
});

// ---------------------------------------------------------------------------
// handleFindingAction — dispatch
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.handleFindingAction', () => {
    it('dispatches accept action to cmdAcceptFinding path', async () => {
        let acceptCalled = false;
        const api = makeApiClient({
            acceptFinding: async () => { acceptCalled = true; return { next: { complete: true } }; },
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.handleFindingAction('accept');

        assert.ok(acceptCalled);
    });

    it('dispatches reject action to cmdRejectFinding path', async () => {
        let rejectCalled = false;
        const api = makeApiClient({
            rejectFinding: async () => { rejectCalled = true; return { next: { complete: true } }; },
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.handleFindingAction('reject');

        assert.ok(rejectCalled);
    });

    it('dispatches exportLearning action', async () => {
        let exported = false;
        const api = makeApiClient({
            exportLearning: async () => { exported = true; return { path: '/out' }; },
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.handleFindingAction('exportLearning');

        assert.ok(exported);
    });

    it('sets indexChangeDismissed and clears notice on dismissIndexChange', async () => {
        const deps = makeDeps({ stateOverrides: { indexChangeDismissed: false } });
        const panel = makeDiscussionPanel();
        deps.ensureDiscussionPanel = () => panel;
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.handleFindingAction('dismissIndexChange');

        assert.equal(deps.state.indexChangeDismissed, true);
        assert.ok(panel._calls.some((c: Call) => c.method === 'clearIndexChangeNotice'));
    });
});
