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
import * as fs from 'fs';
import * as path from 'path';

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
        cmdNextFinding: stub('cmdNextFinding'),
        cmdAcceptFinding: stub('cmdAcceptFinding'),
        cmdRejectFinding: stub('cmdRejectFinding'),
        cmdDiscuss: stub('cmdDiscuss'),
        cmdSelectFinding: stub('cmdSelectFinding') as (index: number) => Promise<void>,
        cmdReviewFinding: stub('cmdReviewFinding'),
        cmdSelectModel: stub('cmdSelectModel'),
        cmdStopServer: () => { calls.push('cmdStopServer'); },
        cmdRefreshSessions: stub('cmdRefreshSessions'),
        cmdViewSession: stub('cmdViewSession') as (item: any) => Promise<void>,
        cmdDeleteSession: stub('cmdDeleteSession') as (item?: any) => Promise<void>,
        cmdRefreshLearning: stub('cmdRefreshLearning'),
        cmdExportLearning: stub('cmdExportLearning'),
        cmdResetLearning: stub('cmdResetLearning'),
        cmdDeleteLearningEntry: stub('cmdDeleteLearningEntry') as (item: any) => Promise<void>,
        cmdRefreshKnowledge: stub('cmdRefreshKnowledge'),
        cmdReviewKnowledge: stub('cmdReviewKnowledge'),
        cmdEditKnowledgeEntry: stub('cmdEditKnowledgeEntry') as (item: any) => Promise<void>,
        cmdResetKnowledgeOverride: stub('cmdResetKnowledgeOverride') as (item?: any) => Promise<void>,
        cmdOpenKnowledgeReviewPanel: stub('cmdOpenKnowledgeReviewPanel') as (item?: any) => Promise<void>,
        cmdNextKnowledgeEntity: stub('cmdNextKnowledgeEntity'),
        cmdPreviousKnowledgeEntity: stub('cmdPreviousKnowledgeEntity'),
    };
}

// ---------------------------------------------------------------------------
// COMMAND_IDS coverage
// ---------------------------------------------------------------------------

const EXPECTED_COMMAND_IDS = [
    'literaryCritic.analyze',
    'literaryCritic.nextFinding',
    'literaryCritic.acceptFinding',
    'literaryCritic.rejectFinding',
    'literaryCritic.discuss',
    'literaryCritic.selectFinding',
    'literaryCritic.reviewFinding',
    'literaryCritic.selectModel',
    'literaryCritic.stopServer',
    'literaryCritic.viewSession',
    'literaryCritic.deleteSession',
    'literaryCritic.refreshLearning',
    'literaryCritic.exportLearning',
    'literaryCritic.resetLearning',
    'literaryCritic.deleteLearningEntry',
    'literaryCritic.refreshKnowledge',
    'literaryCritic.editKnowledgeEntry',
    'literaryCritic.resetKnowledgeOverride',
    'literaryCritic.deleteKnowledgeEntity',
    'literaryCritic.openKnowledgeReviewPanel',
    'literaryCritic.nextKnowledgeEntity',
    'literaryCritic.previousKnowledgeEntity',
    'literaryCritic.toggleEntityLock',
    'literaryCritic.keepFlaggedEntity',
    'literaryCritic.deleteFlaggedEntity',
    'literaryCritic.revealSessionInTree',
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

    it('contains 26 command IDs', () => {
        const { mod } = loadModule();
        assert.equal(mod.COMMAND_IDS.length, 26, 'Expected exactly 26 command IDs');
    });
});

describe('package.json command placement', () => {
    it('places knowledge toolbar commands on their target views', () => {
        const packagePath = path.resolve(__dirname, '../../vscode-extension/package.json');
        const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf-8'));
        const viewTitle = packageJson?.contributes?.menus?.['view/title'] ?? [];
        const viewItemContext = packageJson?.contributes?.menus?.['view/item/context'] ?? [];

        const hasRefreshKnowledgeOnIndexes = viewTitle.some(
            (item: any) => item.command === 'literaryCritic.refreshKnowledge' && item.when === 'view == literaryCritic.indexes',
        );
        const hasReviewKnowledgeOnIndexes = viewTitle.some(
            (item: any) => item.command === 'literaryCritic.reviewKnowledge' && item.when === 'view == literaryCritic.indexes',
        );
        const hasKnowledgePanelInlineAction = viewItemContext.some(
            (item: any) => item.command === 'literaryCritic.openKnowledgeReviewPanel'
                && item.when === 'view == literaryCritic.indexes && (viewItem == knowledgeEntity || viewItem == knowledgeEntityOverridden)'
                && item.group === 'inline',
        );
        const hasResetKnowledgeOnOverriddenEntity = viewItemContext.some(
            (item: any) => item.command === 'literaryCritic.resetKnowledgeOverride'
                && item.when === 'view == literaryCritic.indexes && viewItem == knowledgeEntityOverridden',
        );
        const hasKnowledgePanelNavigationAction = viewItemContext.some(
            (item: any) => item.command === 'literaryCritic.openKnowledgeReviewPanel'
                && item.group === 'navigation',
        );
        const hasKnowledgeQuickEditContextAction = viewItemContext.some(
            (item: any) => item.command === 'literaryCritic.editKnowledgeEntry'
                && item.when === 'view == literaryCritic.indexes && (viewItem == knowledgeEntity || viewItem == knowledgeEntityOverridden)',
        );

        assert.equal(hasRefreshKnowledgeOnIndexes, true);
        assert.equal(hasReviewKnowledgeOnIndexes, false);
        assert.equal(hasKnowledgePanelInlineAction, false);
        assert.equal(hasResetKnowledgeOnOverriddenEntity, true);
        assert.equal(hasKnowledgePanelNavigationAction, false);
        assert.equal(hasKnowledgeQuickEditContextAction, false);
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
            handlerMap.get('literaryCritic.refreshKnowledge'),
            handlers.cmdRefreshKnowledge,
            'refreshKnowledge command should be wired to handlers.cmdRefreshKnowledge',
        );
        assert.equal(
            handlerMap.get('literaryCritic.editKnowledgeEntry'),
            handlers.cmdEditKnowledgeEntry,
            'editKnowledgeEntry command should be wired to handlers.cmdEditKnowledgeEntry',
        );
        assert.equal(
            handlerMap.get('literaryCritic.resetKnowledgeOverride'),
            handlers.cmdResetKnowledgeOverride,
            'resetKnowledgeOverride command should be wired to handlers.cmdResetKnowledgeOverride',
        );
        assert.equal(
            handlerMap.get('literaryCritic.openKnowledgeReviewPanel'),
            handlers.cmdOpenKnowledgeReviewPanel,
            'openKnowledgeReviewPanel command should be wired to handlers.cmdOpenKnowledgeReviewPanel',
        );
        assert.equal(
            handlerMap.get('literaryCritic.nextKnowledgeEntity'),
            handlers.cmdNextKnowledgeEntity,
            'nextKnowledgeEntity command should be wired to handlers.cmdNextKnowledgeEntity',
        );
        assert.equal(
            handlerMap.get('literaryCritic.previousKnowledgeEntity'),
            handlers.cmdPreviousKnowledgeEntity,
            'previousKnowledgeEntity command should be wired to handlers.cmdPreviousKnowledgeEntity',
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
