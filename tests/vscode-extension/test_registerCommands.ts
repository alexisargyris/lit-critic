/**
 * Tests for registerCommands.ts
 *
 * Verifies that:
 *   1. COMMAND_IDS covers exactly the expected set of command identifiers.
 *   2. registerCommands() calls vscode.commands.registerCommand for every ID
 *      in COMMAND_IDS and pushes the disposables to subscriptions.
 *   3. Each handler in CommandHandlers is wired to the correct command ID.
 *
 * All loads go through proxyquire so the real vscode module is never required.
 */

import { strict as assert } from 'assert';

const proxyquire = require('proxyquire').noCallThru();

// ---------------------------------------------------------------------------
// Minimal vscode shim — only the surface used by registerCommands
// ---------------------------------------------------------------------------

function makeVscodeShim() {
    const registered: Array<{ id: string; handler: (...args: any[]) => any }> = [];

    const commands = {
        registerCommand: (id: string, handler: (...args: any[]) => any) => {
            registered.push({ id, handler });
            return { dispose: () => {} };
        },
    };

    return { commands, registered };
}

// ---------------------------------------------------------------------------
// Load registerCommands module via proxyquire
// ---------------------------------------------------------------------------

function loadModule(vscodeShim?: ReturnType<typeof makeVscodeShim>) {
    const shim = vscodeShim ?? makeVscodeShim();
    const mod = proxyquire(
        '../../vscode-extension/src/commands/registerCommands',
        { vscode: shim },
    );
    return { mod, shim };
}

// ---------------------------------------------------------------------------
// Stub handler factory
// ---------------------------------------------------------------------------

function makeStubHandlers() {
    const calls: string[] = [];

    function stub(name: string) {
        return async (..._args: any[]) => { calls.push(name); };
    }

    return {
        calls,
        cmdAnalyze: stub('cmdAnalyze'),
        cmdResume: stub('cmdResume'),
        cmdNextFinding: stub('cmdNextFinding'),
        cmdAcceptFinding: stub('cmdAcceptFinding'),
        cmdRejectFinding: stub('cmdRejectFinding'),
        cmdDiscuss: stub('cmdDiscuss'),
        cmdSelectFinding: stub('cmdSelectFinding') as (index: number) => Promise<void>,
        cmdReviewFinding: stub('cmdReviewFinding'),
        cmdClearSession: stub('cmdClearSession'),
        cmdRerunAnalysis: stub('cmdRerunAnalysis'),
        cmdSelectModel: stub('cmdSelectModel'),
        cmdStopServer: () => { calls.push('cmdStopServer'); },
        cmdRefreshSessions: stub('cmdRefreshSessions'),
        cmdViewSession: stub('cmdViewSession') as (item: any) => Promise<void>,
        cmdDeleteSession: stub('cmdDeleteSession') as (item?: any) => Promise<void>,
        cmdRefreshLearning: stub('cmdRefreshLearning'),
        cmdExportLearning: stub('cmdExportLearning'),
        cmdResetLearning: stub('cmdResetLearning'),
        cmdDeleteLearningEntry: stub('cmdDeleteLearningEntry') as (item: any) => Promise<void>,
    };
}

// ---------------------------------------------------------------------------
// COMMAND_IDS coverage
// ---------------------------------------------------------------------------

const EXPECTED_COMMAND_IDS = [
    'literaryCritic.analyze',
    'literaryCritic.resume',
    'literaryCritic.nextFinding',
    'literaryCritic.acceptFinding',
    'literaryCritic.rejectFinding',
    'literaryCritic.discuss',
    'literaryCritic.selectFinding',
    'literaryCritic.reviewFinding',
    'literaryCritic.clearSession',
    'literaryCritic.rerunAnalysisWithUpdatedIndexes',
    'literaryCritic.selectModel',
    'literaryCritic.stopServer',
    'literaryCritic.refreshSessions',
    'literaryCritic.viewSession',
    'literaryCritic.deleteSession',
    'literaryCritic.refreshLearning',
    'literaryCritic.exportLearning',
    'literaryCritic.resetLearning',
    'literaryCritic.deleteLearningEntry',
];

describe('COMMAND_IDS', () => {
    it('contains exactly the expected command IDs', () => {
        const { mod } = loadModule();
        assert.deepEqual(
            [...mod.COMMAND_IDS].sort(),
            [...EXPECTED_COMMAND_IDS].sort(),
            'COMMAND_IDS must list exactly the expected set of command identifiers',
        );
    });

    it('has no duplicates', () => {
        const { mod } = loadModule();
        const unique = new Set(mod.COMMAND_IDS);
        assert.equal(unique.size, mod.COMMAND_IDS.length, 'COMMAND_IDS must not contain duplicates');
    });

    it('contains 19 command IDs', () => {
        const { mod } = loadModule();
        assert.equal(mod.COMMAND_IDS.length, 19, 'Expected exactly 19 command IDs');
    });
});

// ---------------------------------------------------------------------------
// registerCommands() registration behaviour
// ---------------------------------------------------------------------------

describe('registerCommands()', () => {
    it('calls vscode.commands.registerCommand for every ID in COMMAND_IDS', () => {
        const shim = makeVscodeShim();
        const { mod } = loadModule(shim);

        mod.registerCommands([], makeStubHandlers());

        assert.equal(
            shim.registered.length,
            mod.COMMAND_IDS.length,
            `Expected registerCommand to be called ${mod.COMMAND_IDS.length} times, got ${shim.registered.length}`,
        );
    });

    it('registers a command for every ID in COMMAND_IDS (no IDs missing)', () => {
        const shim = makeVscodeShim();
        const { mod } = loadModule(shim);

        mod.registerCommands([], makeStubHandlers());

        const registeredIds = shim.registered.map((r: any) => r.id);
        for (const id of mod.COMMAND_IDS) {
            assert.ok(
                registeredIds.includes(id),
                `Expected command ID "${id}" to be registered`,
            );
        }
    });

    it('pushes all disposables into the subscriptions array', () => {
        const shim = makeVscodeShim();
        const { mod } = loadModule(shim);

        const subscriptions: any[] = [];
        mod.registerCommands(subscriptions, makeStubHandlers());

        assert.equal(
            subscriptions.length,
            mod.COMMAND_IDS.length,
            'All disposables should be pushed to the subscriptions array',
        );
    });

    it('returns an array of disposables equal in length to COMMAND_IDS', () => {
        const shim = makeVscodeShim();
        const { mod } = loadModule(shim);

        const returned = mod.registerCommands([], makeStubHandlers());

        assert.equal(
            returned.length,
            mod.COMMAND_IDS.length,
            'Returned disposables array length should equal COMMAND_IDS.length',
        );
    });

    it('wires each handler to the correct command ID', () => {
        const shim = makeVscodeShim();
        const { mod } = loadModule(shim);

        const handlers = makeStubHandlers();
        mod.registerCommands([], handlers);

        const handlerMap = new Map(shim.registered.map((r: any) => [r.id, r.handler]));

        assert.equal(
            handlerMap.get('literaryCritic.analyze'),
            handlers.cmdAnalyze,
            'analyze command should be wired to handlers.cmdAnalyze',
        );
        assert.equal(
            handlerMap.get('literaryCritic.resume'),
            handlers.cmdResume,
            'resume command should be wired to handlers.cmdResume',
        );
        assert.equal(
            handlerMap.get('literaryCritic.stopServer'),
            handlers.cmdStopServer,
            'stopServer command should be wired to handlers.cmdStopServer',
        );
        assert.equal(
            handlerMap.get('literaryCritic.deleteLearningEntry'),
            handlers.cmdDeleteLearningEntry,
            'deleteLearningEntry command should be wired to handlers.cmdDeleteLearningEntry',
        );
        assert.equal(
            handlerMap.get('literaryCritic.rerunAnalysisWithUpdatedIndexes'),
            handlers.cmdRerunAnalysis,
            'rerunAnalysis command should be wired to handlers.cmdRerunAnalysis',
        );
    });

    it('the subscriptions array and the returned array contain the same disposables', () => {
        const shim = makeVscodeShim();
        const { mod } = loadModule(shim);

        const subscriptions: any[] = [];
        const returned = mod.registerCommands(subscriptions, makeStubHandlers());

        assert.equal(subscriptions.length, returned.length);
        for (let i = 0; i < returned.length; i++) {
            assert.strictEqual(
                subscriptions[i],
                returned[i],
                `Subscription[${i}] should be the same object as returned[${i}]`,
            );
        }
    });
});
