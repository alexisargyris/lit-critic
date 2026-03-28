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
        refreshKnowledge: async () => ({ scene_updated: 0, index_updated: 0 }),
        getKnowledgeReview: async () => ({ entities: [], overrides: [] }),
        auditScene: async () => ({ deterministic: [], semantic: [], deep: false, model: 'sonnet' }),
        auditIndexes: async () => ({ deterministic: [], semantic: [], placeholder_census: {}, formatted_report: '', deep: false, model: 'sonnet' }),
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
        setSessionContext: () => {},
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

function makeKnowledgeTreeProvider(): any {
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
        knowledgeTreeProvider: makeKnowledgeTreeProvider(),
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
        let capturedItems: any[] | undefined;
        const api = makeApiClient({
            checkSession: async () => ({ exists: true, session_id: undefined }),
            listSessions: async () => ({ sessions: [{ id: 1, status: 'active', depth_mode: 'quick', scene_path: '/s.md', created_at: 't' }] }),
            resumeSessionByIdWithRecovery: async () => {
                resumeByIdCalled = true;
                return { error: null, total_findings: 1, current_index: 0, scene_path: '/s.md', findings_status: [], counts: {}, model: { label: 'm' } };
            },
        });
        const ui = makeUiPort({
            showQuickPick: async (items: any[]) => {
                capturedItems = items;
                // User picks 'Resume' option
                return items.find(i => (typeof i === 'string' ? i : i.label ?? i).toString().startsWith('Resume'));
            },
        });
        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAnalyze();

        assert.ok(resumeByIdCalled, 'should have called resumeSessionByIdWithRecovery');
        assert.ok(Array.isArray(capturedItems));
        assert.ok(
            String(capturedItems?.[0] ?? '').includes('Quick'),
            'single active-session quick pick entry should include session type',
        );
    });

    it('includes session type metadata in multi-active-session quick pick entries', async () => {
        let capturedItems: any[] = [];
        const api = makeApiClient({
            checkSession: async () => ({ exists: true, session_id: undefined }),
            listSessions: async () => ({
                sessions: [
                    { id: 1, status: 'active', depth_mode: 'quick', scene_path: '/quick.md', created_at: 't1' },
                    { id: 2, status: 'active', depth_mode: 'deep', scene_path: '/deep.md', created_at: 't2' },
                ],
            }),
            resumeSessionByIdWithRecovery: async () => ({
                error: null,
                total_findings: 1,
                current_index: 0,
                scene_path: '/quick.md',
                findings_status: [],
                counts: {},
                model: { label: 'm' },
            }),
            getCurrentFinding: async () => ({ complete: true }),
        });

        const ui = makeUiPort({
            showQuickPick: async (items: any[]) => {
                capturedItems = items;
                return items[0];
            },
        });
        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAnalyze();

        const firstResumeItem = capturedItems.find((item) => typeof item === 'object' && String(item.label || '').startsWith('Resume '));
        assert.ok(firstResumeItem, 'expected a resume quick-pick item');
        assert.ok(
            String(firstResumeItem.description || '').includes('Type: Quick'),
            'resume quick-pick description should include type metadata',
        );
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

    it('passes configured analysis mode and syncs model slots before analyze', async () => {
        let capturedMode: string | undefined;
        let capturedSlots: { frontier: string; deep: string; quick: string } | undefined;

        const api = makeApiClient({
            checkSession: async () => ({ exists: false }),
            getConfig: async () => ({
                available_models: { sonnet: { label: 'Sonnet' }, opus: { label: 'Opus' } },
                default_model: 'sonnet',
                analysis_modes: ['quick', 'deep'],
                model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
                default_model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
                mode_cost_hints: {
                    quick: 'Moderate cost (~1.5x quick check baseline)',
                },
            }),
            updateConfigModels: async (slots: { frontier: string; deep: string; quick: string }) => {
                capturedSlots = slots;
                return { model_slots: slots };
            },
            analyze: async (
                _scenePath: string,
                _projectPath: string,
                _apiKey: string | undefined,
                _scenePaths: string[] | undefined,
                mode?: 'quick' | 'deep',
            ) => {
                capturedMode = mode;
                return {
                    scene_path: '/scene.md',
                    scene_name: 'scene.md',
                    project_path: '/project',
                    total_findings: 0,
                    current_index: 0,
                    glossary_issues: [],
                    counts: { critical: 0, major: 0, minor: 0 },
                    lens_counts: {},
                    model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                    learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                    findings_status: [],
                    tier_cost_summary: 'checker tiers only; frontier used for summary/discussion',
                };
            },
            streamAnalysisProgress: (_onEvent: any, onDone: any, _onError: any) => {
                onDone();
                return () => {};
            },
            getCurrentFinding: async () => ({ complete: true }),
        });

        const ui = makeUiPort({
            showOpenDialog: async () => [{ fsPath: '/scene.md' }],
            showTextDocument: async () => undefined,
            getExtensionConfig: () => ({
                inspect: () => undefined,
                get: (key: string, def: any) => {
                    if (key === 'analysisMode') {
                        return 'quick';
                    }
                    if (key === 'modelSlotFrontier') {
                        return 'opus';
                    }
                    if (key === 'modelSlotDeep') {
                        return 'sonnet';
                    }
                    if (key === 'modelSlotQuick') {
                        return 'haiku';
                    }
                    return def;
                },
            } as any),
        });

        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (ui as any)._messages;

        await ctrl.cmdAnalyze();

        assert.equal(capturedMode, 'quick');
        assert.deepEqual(capturedSlots, { frontier: 'opus', deep: 'sonnet', quick: 'haiku' });
        assert.ok(
            messages.some((m) => m.includes('Cost hint (quick): Moderate cost')),
            'Expected pre-run mode cost hint message',
        );
        assert.ok(
            messages.some((m) => m.includes('Tier cost summary: checker tiers only; frontier used for summary/discussion')),
            'Expected post-run tier cost summary message',
        );
    });

    it('warns and continues when model-slot sync fails before analyze', async () => {
        let analyzeCalled = false;

        const api = makeApiClient({
            checkSession: async () => ({ exists: false }),
            getConfig: async () => ({
                available_models: { sonnet: { label: 'Sonnet' }, opus: { label: 'Opus' } },
                default_model: 'sonnet',
                analysis_modes: ['quick', 'deep'],
                model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
                default_model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
            }),
            updateConfigModels: async () => {
                throw new Error('network down');
            },
            analyze: async () => {
                analyzeCalled = true;
                return {
                    scene_path: '/scene.md',
                    scene_name: 'scene.md',
                    project_path: '/project',
                    total_findings: 0,
                    current_index: 0,
                    glossary_issues: [],
                    counts: { critical: 0, major: 0, minor: 0 },
                    lens_counts: {},
                    model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                    learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                    findings_status: [],
                };
            },
            streamAnalysisProgress: (_onEvent: any, onDone: any, _onError: any) => {
                onDone();
                return () => {};
            },
            getCurrentFinding: async () => ({ complete: true }),
        });

        const ui = makeUiPort({
            showOpenDialog: async () => [{ fsPath: '/scene.md' }],
            showTextDocument: async () => undefined,
            getExtensionConfig: () => ({
                inspect: () => undefined,
                get: (key: string, def: any) => {
                    if (key === 'analysisMode') {
                        return 'quick';
                    }
                    if (key === 'modelSlotFrontier') {
                        return 'opus';
                    }
                    if (key === 'modelSlotDeep') {
                        return 'sonnet';
                    }
                    if (key === 'modelSlotQuick') {
                        return 'haiku';
                    }
                    return def;
                },
            } as any),
        });

        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (ui as any)._messages;

        await ctrl.cmdAnalyze();

        assert.equal(analyzeCalled, true, 'analysis should continue even if slot sync fails');
        assert.ok(
            messages.some((m) => m.includes('Could not sync model slots before analysis (network down)')),
            'Expected warning when model-slot sync fails',
        );
    });
});

// ---------------------------------------------------------------------------
// cmdResume
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdAnalyze (resume path)', () => {
    it('resets closedSessionNotice and indexChangeDismissed before resuming', async () => {
        const deps = makeDeps({ stateOverrides: { closedSessionNotice: 'old notice', indexChangeDismissed: true } });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAnalyze();

        assert.equal(deps.state.closedSessionNotice, undefined);
        assert.equal(deps.state.indexChangeDismissed, false);
    });

    it('shows error when no project path detected', async () => {
        const deps = makeDeps({ detectProjectPath: () => undefined });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdAnalyze();

        assert.ok(messages.some(m => m.includes('Could not detect project')));
    });

    it('shows error message when resume returns error', async () => {
        const api = makeApiClient({
            checkSession: async () => ({ exists: true }),
            resumeWithRecovery: async () => ({ error: 'No session found', total_findings: 0, current_index: 0, scene_path: '', findings_status: [], counts: {}, model: { label: 'm' } }),
        });
        const deps = makeDeps({
            apiClient: api,
            ui: { showQuickPick: async () => ({ label: 'Resume existing session' }) },
        });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdAnalyze();

        assert.ok(messages.some(m => m.includes('Resume failed')));
    });

    it('shows success info message on happy path', async () => {
        const api = makeApiClient({ checkSession: async () => ({ exists: true }) });
        const deps = makeDeps({
            apiClient: api,
            ui: { showQuickPick: async () => ({ label: 'Resume existing session' }) },
        });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdAnalyze();

        assert.ok(messages.some(m => m.includes('Resumed session')));
    });

    it('opens all resolved scene files for multi-scene resume without forcing a target view column', async () => {
        const opened: Array<{ fsPath: string; options?: any }> = [];
        const api = makeApiClient({
            checkSession: async () => ({ exists: true }),
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
                showQuickPick: async () => ({ label: 'Resume existing session' }),
                pathExists: (p: string) => p === '/scene-1.md' || p === '/scene-2.md',
                showTextDocument: async (fsPath: string, options?: any) => {
                    opened.push({ fsPath, options });
                    return undefined;
                },
            },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAnalyze();

        assert.deepEqual(opened.map((entry) => entry.fsPath), ['/scene-1.md', '/scene-2.md']);
        assert.equal(opened[0].options?.viewColumn, undefined);
        assert.equal(opened[1].options?.viewColumn, undefined);
    });

    it('opens only missing scene files when others are already open across groups', async () => {
        const opened: Array<{ fsPath: string; options?: any }> = [];
        const api = makeApiClient({
            checkSession: async () => ({ exists: true }),
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
                showQuickPick: async () => ({ label: 'Resume existing session' }),
                pathExists: (p: string) =>
                    p === '/scene-1.md' || p === '/scene-2.md' || p === '/scene-3.md',
                getOpenTextDocumentPaths: () => ['/SCENE-1.md', '/scene-3.md'],
                showTextDocument: async (fsPath: string, options?: any) => {
                    opened.push({ fsPath, options });
                    return undefined;
                },
            },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdAnalyze();

        assert.deepEqual(opened.map((entry) => entry.fsPath), ['/scene-2.md']);
        assert.equal(opened[0].options?.viewColumn, undefined);
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

describe('SessionWorkflowController.cmdDeleteSession', () => {
    it('does not clear when user does not confirm', async () => {
        let clearCalled = false;
        const api = makeApiClient({ clearSession: async () => { clearCalled = true; } });
        const deps = makeDeps({
            apiClient: api,
            ui: { showWarningMessage: async () => undefined },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdDeleteSession();

        assert.ok(!clearCalled, 'clearSession should not be called when user cancels');
    });

    it('shows info message when user confirms session deletion', async () => {
        const deps = makeDeps({
            ui: { showWarningMessage: async () => 'Delete' },
        });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdDeleteSession({ session: { id: 99 } });

        assert.ok(messages.some(m => m.includes('deleted')), 'expected deleted confirmation message');
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
// cmdRefreshKnowledge
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdRefreshKnowledge', () => {
    it('shows extraction-skipped note when refresh has no stale scenes', async () => {
        const api = makeApiClient({
            refreshKnowledge: async () => ({
                scene_updated: 0,
                index_updated: 1,
                extraction: {
                    reason: 'no_stale_scenes',
                    failed: [],
                },
            }),
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdRefreshKnowledge();

        assert.ok(
            messages.some((m) => m.includes('Knowledge refreshed (0 scenes, 1 indexes updated). Extraction skipped (no stale scenes).')),
            'expected refresh info message to include no-stale-scenes extraction note',
        );
        assert.ok(
            !messages.some((m) => m.includes('Knowledge extraction issue')),
            'did not expect extraction warning for no_stale_scenes',
        );
    });

    it('shows extraction warning when extraction is unavailable', async () => {
        const api = makeApiClient({
            refreshKnowledge: async () => ({
                scene_updated: 1,
                index_updated: 0,
                extraction: {
                    reason: 'extraction_unavailable',
                    error: 'No API key for provider',
                    failed: [],
                },
            }),
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdRefreshKnowledge();

        // When extraction is unavailable, the controller shows a warning (not an info message).
        // The warning replaces the "Knowledge refreshed" info message for this case.
        assert.ok(
            !messages.some((m) => m.startsWith('info:') && m.includes('Knowledge refreshed')),
            'did not expect a Knowledge refreshed info message when extraction is unavailable',
        );
        assert.ok(
            messages.some(
                (m) => m.startsWith('warn:') && m.includes('extraction failed (extraction_unavailable)') && m.includes('Categories may remain empty.'),
            ),
            'expected warning message explaining extraction is unavailable',
        );
    });
});

// ---------------------------------------------------------------------------
// cmdEditKnowledgeEntry / cmdResetKnowledgeOverride
// ---------------------------------------------------------------------------

describe('SessionWorkflowController knowledge override commands', () => {
    it('submits override and refreshes tree for selected knowledge field', async () => {
        const submitCalls: Array<[string, string, string, string, string]> = [];
        let refreshCount = 0;
        const api = makeApiClient({
            submitOverride: async (...args: [string, string, string, string, string]) => {
                submitCalls.push(args);
                return { updated: true, category: args[0], entity_key: args[1], field_name: args[2] };
            },
        });
        const knowledgeTreeProvider = {
            setApiClient: () => {},
            setProjectPath: () => {},
            refresh: async () => { refreshCount += 1; },
            setFlaggedEntities: () => {},
            clearFlaggedEntities: () => {},
        };
        const ui = makeUiPort({
            showQuickPick: async (items: any[]) => items.find((item: any) => item.label === 'category'),
            showInputBox: async () => 'Protagonist',
        });
        const deps = {
            ...makeDeps({ apiClient: api, ui }),
            knowledgeTreeProvider,
        } as WorkflowDeps;
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (ui as any)._messages;

        await ctrl.cmdEditKnowledgeEntry({
            category: 'characters',
            entityKey: 'char:alice',
            label: 'Alice',
            entity: { entity_key: 'char:alice', name: 'Alice', category: 'Lead' },
            overrideFields: ['category'],
            overrideCount: 1,
            hasOverrides: true,
        });

        assert.deepEqual(submitCalls, [[
            'characters',
            'char:alice',
            'category',
            'Protagonist',
            '/project',
        ]]);
        assert.equal(refreshCount, 1);
        assert.ok(messages.some((m) => m.includes('Saved category override for Alice.')));
    });

    it('keeps the V1 edit flow working for tree items that wrap the knowledge payload', async () => {
        const submitCalls: Array<[string, string, string, string, string]> = [];
        let refreshCount = 0;
        const api = makeApiClient({
            submitOverride: async (...args: [string, string, string, string, string]) => {
                submitCalls.push(args);
                return { updated: true, category: args[0], entity_key: args[1], field_name: args[2] };
            },
        });
        const knowledgeTreeProvider = {
            setApiClient: () => {},
            setProjectPath: () => {},
            refresh: async () => { refreshCount += 1; },
            setFlaggedEntities: () => {},
            clearFlaggedEntities: () => {},
        };
        const ui = makeUiPort({
            showQuickPick: async (items: any[]) => items.find((item: any) => item.label === 'name'),
            showInputBox: async () => 'Alice Liddell',
        });
        const deps = {
            ...makeDeps({ apiClient: api, ui }),
            knowledgeTreeProvider,
        } as WorkflowDeps;
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdEditKnowledgeEntry({
            payload: {
                category: 'characters',
                entityKey: 'char:alice',
                label: 'Alice',
                entity: { entity_key: 'char:alice', name: 'Alice', role: 'Lead' },
                overrideFields: ['role'],
                overrideCount: 1,
                hasOverrides: true,
            },
        });

        assert.deepEqual(submitCalls, [[
            'characters',
            'char:alice',
            'name',
            'Alice Liddell',
            '/project',
        ]]);
        assert.equal(refreshCount, 1);
    });

    it('stops edit flow when payload is malformed', async () => {
        let submitCalled = false;
        const api = makeApiClient({
            submitOverride: async () => {
                submitCalled = true;
                return { updated: true, category: 'characters', entity_key: 'x', field_name: 'name' };
            },
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdEditKnowledgeEntry({ label: 'Bad payload' });

        assert.equal(submitCalled, false);
        assert.ok(messages.some((m) => m.includes('Could not determine knowledge entry to edit.')));
    });

    it('does not submit override when quick pick is cancelled', async () => {
        let submitCalled = false;
        const api = makeApiClient({
            submitOverride: async () => {
                submitCalled = true;
                return { updated: true, category: 'characters', entity_key: 'x', field_name: 'name' };
            },
        });
        const ui = makeUiPort({ showQuickPick: async () => undefined });
        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdEditKnowledgeEntry({
            category: 'characters',
            entityKey: 'char:alice',
            label: 'Alice',
            entity: { entity_key: 'char:alice', name: 'Alice', category: 'Lead' },
            overrideFields: [],
            overrideCount: 0,
            hasOverrides: false,
        });

        assert.equal(submitCalled, false);
    });

    it('resets selected override field and refreshes tree', async () => {
        const deleteCalls: Array<[string, string, string, string]> = [];
        let refreshCount = 0;
        const api = makeApiClient({
            deleteOverride: async (...args: [string, string, string, string]) => {
                deleteCalls.push(args);
                return { deleted: true, category: args[0], entity_key: args[1], field_name: args[2] };
            },
        });
        const knowledgeTreeProvider = {
            setApiClient: () => {},
            setProjectPath: () => {},
            refresh: async () => { refreshCount += 1; },
            setFlaggedEntities: () => {},
            clearFlaggedEntities: () => {},
        };
        const ui = makeUiPort({
            showQuickPick: async (items: any[]) => items.find((item: any) => item.label === 'role'),
        });
        const deps = {
            ...makeDeps({ apiClient: api, ui }),
            knowledgeTreeProvider,
        } as WorkflowDeps;
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (ui as any)._messages;

        await ctrl.cmdResetKnowledgeOverride({
            category: 'characters',
            entityKey: 'char:alice',
            label: 'Alice',
            entity: { entity_key: 'char:alice', name: 'Alice', role: 'Lead' },
            overrideFields: ['category', 'role'],
            overrideCount: 2,
            hasOverrides: true,
        });

        assert.deepEqual(deleteCalls, [[
            'characters',
            'char:alice',
            'role',
            '/project',
        ]]);
        assert.equal(refreshCount, 1);
        assert.ok(messages.some((m) => m.includes('Reset role override for Alice.')));
    });

    it('shows error when reset is requested for an entity without overrides', async () => {
        let deleteCalled = false;
        const api = makeApiClient({
            deleteOverride: async () => {
                deleteCalled = true;
                return { deleted: true, category: 'characters', entity_key: 'x', field_name: 'name' };
            },
        });
        const deps = makeDeps({ apiClient: api });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (deps.ui as any)._messages;

        await ctrl.cmdResetKnowledgeOverride({
            category: 'characters',
            entityKey: 'char:alice',
            label: 'Alice',
            entity: { entity_key: 'char:alice', name: 'Alice' },
            overrideFields: [],
            overrideCount: 0,
            hasOverrides: false,
        });

        assert.equal(deleteCalled, false);
        assert.ok(messages.some((m) => m.includes('has no overrides to reset')));
    });
});

// ---------------------------------------------------------------------------
// cmdSelectModel
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.cmdSelectModel', () => {
    it('preselects the currently configured analysis mode in quick pick', async () => {
        const quickPickCalls: Array<{ items: any[]; options?: any }> = [];
        let updatedMode: string | undefined;

        const api = makeApiClient({
            getConfig: async () => ({
                available_models: { sonnet: { label: 'Sonnet 4.5' } },
                default_model: 'sonnet',
                analysis_modes: ['quick', 'deep'],
                model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
                default_model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
            }),
        });

        const ui = makeUiPort({
            showQuickPick: async (items: any[], options?: any) => {
                quickPickCalls.push({ items, options });
                if (quickPickCalls.length === 1) {
                    return items.find((i: any) => i.action === 'analysisMode');
                }
                return items.find((i: any) => i.label === 'quick');
            },
            getExtensionConfig: () => ({
                inspect: (_key: string) => undefined,
                get: (key: string, def: any) => {
                    if (key === 'analysisMode') {
                        return 'deep';
                    }
                    return def;
                },
                update: async (key: string, value: string) => {
                    if (key === 'analysisMode') {
                        updatedMode = value;
                    }
                },
            } as any),
        });

        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdSelectModel();

        assert.equal(quickPickCalls.length, 2, 'Expected two quick pick invocations');
        assert.equal(quickPickCalls[0].options?.placeHolder, 'Select setting to configure');
        assert.equal(quickPickCalls[1].options?.activeItemLabel, 'deep');
        assert.ok(
            quickPickCalls[1].items.some((item: any) => item.label === 'deep' && item.detail === 'Current mode'),
            'Expected currently configured mode to be marked as Current mode',
        );
        assert.equal(updatedMode, 'quick');
    });

    it('updates selected model slot from available models', async () => {
        const quickPickCalls: Array<{ items: any[]; options?: any }> = [];
        const updates: Array<{ key: string; value: string; target: number }> = [];

        const api = makeApiClient({
            getConfig: async () => ({
                available_models: {
                    sonnet: { label: 'Sonnet 4.5', provider: 'anthropic' },
                    opus: { label: 'Opus 4.1', provider: 'anthropic' },
                },
                default_model: 'sonnet',
                analysis_modes: ['quick', 'deep'],
                model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
                default_model_slots: { frontier: 'sonnet', deep: 'sonnet', quick: 'haiku' },
            }),
        });

        const ui = makeUiPort({
            showQuickPick: async (items: any[], options?: any) => {
                quickPickCalls.push({ items, options });
                if (quickPickCalls.length === 1) {
                    return items.find((i: any) => i.action === 'modelSlotDeep');
                }
                return items.find((i: any) => i.value === 'opus');
            },
            getExtensionConfig: () => ({
                inspect: (_key: string) => undefined,
                get: (key: string, def: any) => {
                    if (key === 'analysisMode') {
                        return 'deep';
                    }
                    return def;
                },
                update: async (key: string, value: string, target: number) => {
                    updates.push({ key, value, target });
                },
            } as any),
        });

        const deps = makeDeps({ apiClient: api, ui });
        const ctrl = new SessionWorkflowController(deps);
        const messages: string[] = (ui as any)._messages;

        await ctrl.cmdSelectModel();

        assert.equal(quickPickCalls.length, 2, 'Expected action + model picker quick picks');
        assert.equal(quickPickCalls[1].options?.placeHolder, 'Select model for Deep slot');
        assert.deepEqual(updates, [{ key: 'modelSlotDeep', value: 'opus', target: 2 }]);
        assert.ok(
            messages.some((m) => m.includes('Deep slot set to Opus 4.1 (opus).')),
            'Expected success message for updated deep slot',
        );
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

    it('loads a completed session in read-only mode without resuming it', async () => {
        const messages: string[] = [];
        const viewCalls: boolean[] = [];
        const api = makeApiClient({
            getSessionDetail: async () => ({ id: 7, status: 'completed', scene_path: '/scene-1.md', current_index: 0 }),
            resumeSessionByIdWithRecovery: async () => {
                throw new Error('should not resume completed session');
            },
            viewSessionWithRecovery: async (_projectPath: string, sessionId: number, _scenePath?: string, _prompt?: unknown, reopen = false) => {
                viewCalls.push(reopen);
                return {
                    error: null,
                    session_id: sessionId,
                    total_findings: 1,
                    current_index: 0,
                    scene_path: '/scene-1.md',
                    scene_paths: ['/scene-1.md'],
                    findings_status: [{ number: 1, severity: 'major', lens: 'style', location: 'Paragraph 1', status: 'pending' }],
                    counts: { critical: 0, major: 1, minor: 0 },
                    model: { label: 'm' },
                };
            },
            getCurrentFinding: async () => ({
                complete: false,
                finding: {
                    number: 1,
                    severity: 'major',
                    lens: 'style',
                    location: 'Paragraph 1',
                    line_start: 1,
                    line_end: 1,
                    scene_path: '/scene-1.md',
                    evidence: 'Example',
                    impact: '',
                    options: [],
                    flagged_by: [],
                    ambiguity_type: null,
                    stale: false,
                    status: 'pending',
                },
                current: 1,
                total: 1,
                is_ambiguity: false,
            }),
        });
        const deps = makeDeps({
            apiClient: api,
            ui: {
                pathExists: () => true,
                showTextDocument: async () => undefined,
                showInformationMessage: async (m: string) => { messages.push(m); return undefined; },
            },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdViewSession({ session: { id: 7 } });

        assert.deepEqual(viewCalls, [false]);
        assert.equal(deps.state.closedSessionNotice, 'Viewing completed session — actions will reopen it.');
        assert.ok(messages.some((m) => m.includes('Viewing completed session: 1 findings')));
    });
});

// ---------------------------------------------------------------------------
// handleFindingAction — dispatch
// ---------------------------------------------------------------------------

describe('SessionWorkflowController.handleFindingAction', () => {
    it('reopens a viewed closed session before accepting a finding', async () => {
        const events: string[] = [];
        const api = makeApiClient({
            getSessionDetail: async () => ({ id: 7, status: 'completed', scene_path: '/scene-1.md', current_index: 0 }),
            viewSessionWithRecovery: async (_projectPath: string, sessionId: number, _scenePath?: string, _prompt?: unknown, reopen = false) => {
                events.push(`view:${reopen}`);
                return {
                    error: null,
                    session_id: sessionId,
                    total_findings: 1,
                    current_index: 0,
                    scene_path: '/scene-1.md',
                    scene_paths: ['/scene-1.md'],
                    findings_status: [{ number: 1, severity: 'major', lens: 'style', location: 'Paragraph 1', status: 'pending' }],
                    counts: { critical: 0, major: 1, minor: 0 },
                    model: { label: 'm' },
                };
            },
            getCurrentFinding: async () => ({
                complete: false,
                finding: {
                    number: 1,
                    severity: 'major',
                    lens: 'style',
                    location: 'Paragraph 1',
                    line_start: 1,
                    line_end: 1,
                    scene_path: '/scene-1.md',
                    evidence: 'Example',
                    impact: '',
                    options: [],
                    flagged_by: [],
                    ambiguity_type: null,
                    stale: false,
                    status: 'pending',
                },
                current: 1,
                total: 1,
                is_ambiguity: false,
            }),
            acceptFinding: async () => {
                events.push('accept');
                return { next: { complete: false, finding: null, current: 1, total: 1 } };
            },
        });
        const messages: string[] = [];
        const deps = makeDeps({
            apiClient: api,
            ui: {
                pathExists: () => true,
                showTextDocument: async () => undefined,
                showInformationMessage: async (m: string) => { messages.push(m); return undefined; },
            },
            stateOverrides: { allFindings: [], currentFindingIndex: 0 },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdViewSession({ session: { id: 7 } });
        await ctrl.handleFindingAction('accept');

        assert.deepEqual(events.filter((event) => event.startsWith('view:')), ['view:false', 'view:true']);
        assert.ok(events.indexOf('accept') > events.indexOf('view:true'));
        assert.equal(deps.state.closedSessionNotice, undefined);
        assert.equal(deps.state.allFindings[0].status, 'accepted');
        assert.ok(messages.some((m) => m.includes('Session reopened for editing.')));
    });

    it('reopens a viewed closed session before marking ambiguity', async () => {
        const events: string[] = [];
        const api = makeApiClient({
            getSessionDetail: async () => ({ id: 7, status: 'abandoned', scene_path: '/scene-1.md', current_index: 0 }),
            viewSessionWithRecovery: async (_projectPath: string, sessionId: number, _scenePath?: string, _prompt?: unknown, reopen = false) => {
                events.push(`view:${reopen}`);
                return {
                    error: null,
                    session_id: sessionId,
                    total_findings: 1,
                    current_index: 0,
                    scene_path: '/scene-1.md',
                    scene_paths: ['/scene-1.md'],
                    findings_status: [{ number: 1, severity: 'major', lens: 'style', location: 'Paragraph 1', status: 'pending' }],
                    counts: { critical: 0, major: 1, minor: 0 },
                    model: { label: 'm' },
                };
            },
            getCurrentFinding: async () => ({
                complete: false,
                finding: {
                    number: 1,
                    severity: 'major',
                    lens: 'style',
                    location: 'Paragraph 1',
                    line_start: 1,
                    line_end: 1,
                    scene_path: '/scene-1.md',
                    evidence: 'Example',
                    impact: '',
                    options: [],
                    flagged_by: [],
                    ambiguity_type: null,
                    stale: false,
                    status: 'pending',
                },
                current: 1,
                total: 1,
                is_ambiguity: false,
            }),
            markAmbiguity: async () => {
                events.push('ambiguity');
            },
        });
        const messages: string[] = [];
        const deps = makeDeps({
            apiClient: api,
            ui: {
                pathExists: () => true,
                showTextDocument: async () => undefined,
                showInformationMessage: async (m: string) => { messages.push(m); return undefined; },
            },
        });
        const ctrl = new SessionWorkflowController(deps);

        await ctrl.cmdViewSession({ session: { id: 7 } });
        await ctrl.handleFindingAction('ambiguity', true);

        assert.deepEqual(events, ['view:false', 'view:true', 'ambiguity']);
        assert.equal(deps.state.closedSessionNotice, undefined);
        assert.ok(messages.some((m) => m.includes('Session reopened for editing.')));
        assert.ok(messages.some((m) => m.includes('Marked as intentional')));
    });

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
