import { strict as assert } from 'assert';

import { cmdSelectModel } from '../../vscode-extension/src/workflows/modelSelectionWorkflow';
import { WorkflowDeps } from '../../vscode-extension/src/workflows/sessionWorkflowController';

// ---------------------------------------------------------------------------
// Canned server config
// ---------------------------------------------------------------------------

const cannedConfig = {
    api_key_configured: true,
    available_models: {
        sonnet: { label: 'Sonnet 4.5', provider: 'anthropic' },
        haiku: { label: 'Haiku 4.5', provider: 'anthropic' },
        opus: { label: 'Opus 4.6', provider: 'anthropic' },
    },
    default_model: 'sonnet',
    analysis_modes: ['quick', 'deep'],
    model_slots: { frontier: 'opus', deep: 'sonnet', quick: 'haiku' },
};

// ---------------------------------------------------------------------------
// Mock deps factory
// ---------------------------------------------------------------------------

function makeTrackedDeps(configOverrides: Record<string, any> = {}) {
    const infoMessages: string[] = [];
    const errorMessages: string[] = [];
    const configUpdates: Array<{ key: string; value: any; target: number }> = [];
    const quickPickCalls: Array<{ items: any[]; options: any }> = [];
    let quickPickResponses: any[] = [];
    let qpCallIndex = 0;

    const extConfig = {
        get: (key: string, defaultValue: any) => configOverrides[key] ?? defaultValue,
        inspect: () => undefined,
        update: async (key: string, value: any, target: number) => {
            configUpdates.push({ key, value, target });
        },
    };

    const deps: WorkflowDeps = {
        getApiClient: () => ({
            getConfig: async () => ({ ...cannedConfig }),
        } as any),
        ensureServer: async () => {},
        getServerManager: () => ({ isRunning: true, stop: () => {} } as any),
        state: {} as any,
        presenter: { setError: () => {} } as any,
        findingsTreeProvider: {} as any,
        sessionsTreeProvider: {} as any,
        learningTreeProvider: {} as any,
        knowledgeTreeProvider: {} as any,
        knowledgeTreeView: undefined,
        diagnosticsProvider: {} as any,
        ensureDiscussionPanel: () => ({} as any),
        getDiscussionPanel: () => undefined,
        runTrackedOperation: async (_p, op) => op(),
        detectProjectPath: () => '/project',
        promptForScenePathOverride: async () => undefined,
        ui: {
            showInformationMessage: async (msg: string) => { infoMessages.push(msg); return undefined; },
            showErrorMessage: async (msg: string) => { errorMessages.push(msg); return undefined; },
            showWarningMessage: async () => undefined,
            showInputBox: async () => undefined,
            showQuickPick: async (items: any[], options: any) => {
                quickPickCalls.push({ items, options });
                const resp = quickPickResponses[qpCallIndex++];
                return resp;
            },
            showOpenDialog: async () => undefined,
            showTextDocument: async () => ({}),
            withProgress: async (_t, task) => task({ report: () => {} }),
            navigateToFindingLine: async () => {},
            pathExists: () => true,
            getOpenTextDocumentPaths: () => [],
            getExtensionConfig: () => extConfig,
        },
    };

    return {
        deps,
        infoMessages,
        errorMessages,
        configUpdates,
        quickPickCalls,
        // Provide responses for successive quickPick calls
        setQuickPickResponses(...responses: any[]) {
            quickPickResponses = responses;
            qpCallIndex = 0;
        },
    };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('modelSelectionWorkflow — cmdSelectModel()', () => {
    it('user cancels first picker — no writes', async () => {
        const t = makeTrackedDeps();
        t.setQuickPickResponses(undefined); // cancel action picker
        await cmdSelectModel(t.deps);
        assert.equal(t.configUpdates.length, 0);
    });

    it('mode-picker: mode updated in config when user selects', async () => {
        const t = makeTrackedDeps({ analysisMode: 'quick' });
        t.setQuickPickResponses(
            { action: 'analysisMode', label: 'Set analysis mode' },  // action picker
            { label: 'deep' },                                        // mode picker
        );
        await cmdSelectModel(t.deps);
        assert.equal(t.configUpdates.length, 1);
        assert.equal(t.configUpdates[0].key, 'analysisMode');
        assert.equal(t.configUpdates[0].value, 'deep');
        assert.ok(t.infoMessages.some(m => m.includes('Analysis mode set to deep')));
    });

    it('mode-picker: user cancels mode pick — no writes', async () => {
        const t = makeTrackedDeps();
        t.setQuickPickResponses(
            { action: 'analysisMode', label: 'Set analysis mode' }, // action picker
            undefined,                                               // user cancels mode pick
        );
        await cmdSelectModel(t.deps);
        assert.equal(t.configUpdates.length, 0);
    });

    it('slot-picker: frontier slot set to specific model', async () => {
        const t = makeTrackedDeps();
        t.setQuickPickResponses(
            { action: 'modelSlotFrontier', label: 'Set Frontier model slot' }, // action picker
            { label: 'Sonnet 4.5 (sonnet)', value: 'sonnet' },                 // model picker
        );
        await cmdSelectModel(t.deps);
        assert.equal(t.configUpdates.length, 1);
        assert.equal(t.configUpdates[0].key, 'modelSlotFrontier');
        assert.equal(t.configUpdates[0].value, 'sonnet');
        assert.ok(t.infoMessages.some(m => m.includes('Frontier slot set to')));
    });

    it('slot-picker: "Use backend default" writes empty string', async () => {
        const t = makeTrackedDeps();
        t.setQuickPickResponses(
            { action: 'modelSlotDeep', label: 'Set Deep model slot' }, // action picker
            { label: 'Use backend default', value: '' },                // backend default
        );
        await cmdSelectModel(t.deps);
        assert.equal(t.configUpdates.length, 1);
        assert.equal(t.configUpdates[0].key, 'modelSlotDeep');
        assert.equal(t.configUpdates[0].value, '');
        assert.ok(t.infoMessages.some(m => m.includes('backend default')));
    });

    it('slot-picker: user cancels model pick — no writes', async () => {
        const t = makeTrackedDeps();
        t.setQuickPickResponses(
            { action: 'modelSlotQuick', label: 'Set Quick model slot' }, // action picker
            undefined,                                                    // user cancels
        );
        await cmdSelectModel(t.deps);
        assert.equal(t.configUpdates.length, 0);
    });

    it('action picker shows current mode in description', async () => {
        const t = makeTrackedDeps({ analysisMode: 'deep' });
        t.setQuickPickResponses(undefined); // cancel immediately
        await cmdSelectModel(t.deps);
        const firstPickCall = t.quickPickCalls[0];
        const modeActionItem = firstPickCall?.items.find((i: any) => i.action === 'analysisMode');
        assert.ok(modeActionItem, 'Expected analysisMode action item');
        assert.ok(modeActionItem.description?.includes('deep'));
    });
});
