import { strict as assert } from 'assert';

import { createFreshMockVscode, MockWebviewView } from './fixtures';
import { getKnowledgeReviewPanelHtml } from '../../vscode-extension/src/ui/knowledgeReviewPanelView';

const proxyquire = require('proxyquire').noCallThru();

function makePanelState() {
    return {
        category: 'characters' as const,
        categoryLabel: 'Characters',
        entityKey: 'char:alice',
        entityLabel: 'Alice',
        fields: [
            {
                fieldName: 'role',
                fieldLabel: 'Role',
                extractedValue: 'Lead',
                overrideValue: 'Protagonist',
                effectiveValue: 'Protagonist',
                draftValue: 'Protagonist',
                hasOverride: true,
                isDirty: false,
                stateColor: 'overridden' as const,
            },
            {
                fieldName: 'alias',
                fieldLabel: 'Alias',
                extractedValue: 'Al',
                overrideValue: null,
                effectiveValue: 'Al',
                draftValue: 'Al',
                hasOverride: false,
                isDirty: false,
                stateColor: null,
            },
        ],
        selectedFieldName: 'role',
        stale: false,
        flagged: false,
        hasOverrides: true,
        locked: false,
        dirty: false,
        status: 'idle' as const,
        statusMessage: undefined,
        lastSavedAt: null,
    };
}

function flushMicrotasks(): Promise<void> {
    return new Promise((resolve) => setImmediate(resolve));
}

describe('KnowledgeReviewPanel (Real)', () => {
    let KnowledgeReviewViewProvider: any;
    let mockVscode: any;
    let panel: any;
    let mockWebviewView: MockWebviewView;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();
        mockWebviewView = new MockWebviewView();

        const module = proxyquire('../../vscode-extension/src/knowledgeReviewViewProvider', {
            vscode: mockVscode,
        });
        KnowledgeReviewViewProvider = module.KnowledgeReviewViewProvider;
        panel = new KnowledgeReviewViewProvider();
        // Simulate VS Code calling resolveWebviewView when the sidebar section opens
        panel.resolveWebviewView(mockWebviewView, {}, {});
    });

    afterEach(() => {
        panel?.dispose();
    });

    it('renders HTML with review state on show', () => {
        const state = makePanelState();

        panel.show(state);
        state.fields[0].draftValue = 'Mutated outside panel';

        const currentState = panel.getState();
        assert.ok(currentState);
        assert.equal(currentState.entityLabel, 'Alice');
        assert.equal(currentState.fields[0].draftValue, 'Protagonist');
        assert.match(mockWebviewView.webview.html, /Alice/);
        assert.match(mockWebviewView.webview.html, /Protagonist/);
        assert.match(mockWebviewView.webview.html, /Lead/);
    });

    it('posts refreshed state to the existing webview on updateState', () => {
        panel.show(makePanelState());

        let postedMessage: any;
        mockWebviewView.webview.postMessage = (message: any) => {
            postedMessage = message;
        };

        panel.updateState({
            ...makePanelState(),
            status: 'saved',
            statusMessage: 'Saved role override.',
            lastSavedAt: '2026-03-14T10:00:00Z',
        });

        assert.equal(postedMessage?.type, 'setState');
        assert.equal(postedMessage?.state?.status, 'saved');
        assert.equal(postedMessage?.state?.statusMessage, 'Saved role override.');
        assert.equal(postedMessage?.state?.fields?.[0]?.overrideValue, 'Protagonist');
    });

    it('updates draft state and forwards change-field actions from the webview', async () => {
        const actions: any[] = [];
        const posted: any[] = [];

        panel.onAction = async (action: any) => {
            actions.push(action);
        };
        panel.show(makePanelState());
        mockWebviewView.webview.postMessage = (message: any) => {
            posted.push(message);
        };

        mockWebviewView._simulateMessage({ type: 'change-field', fieldName: 'alias', value: 'Ace' });
        await flushMicrotasks();

        const currentState = panel.getState();
        const aliasField = currentState?.fields.find((field: any) => field.fieldName === 'alias');
        assert.equal(aliasField?.draftValue, 'Ace');
        assert.equal(aliasField?.isDirty, true);
        assert.equal(currentState?.dirty, true);
        assert.equal(currentState?.selectedFieldName, 'alias');
        assert.equal(currentState?.status, 'dirty');
        // No setState posted — provider intentionally skips render() on change-field to preserve textarea focus.
        assert.deepEqual(actions, [{ type: 'change-field', fieldName: 'alias', value: 'Ace' }]);
    });

    it('forwards save/reset/navigation actions to the controller callback', async () => {
        const actions: any[] = [];
        panel.onAction = async (action: any) => {
            actions.push(action);
        };
        panel.show(makePanelState());

        mockWebviewView._simulateMessage({ type: 'save-field', fieldName: 'role', value: 'Captain' });
        mockWebviewView._simulateMessage({ type: 'reset-field', fieldName: 'role' });
        mockWebviewView._simulateMessage({ type: 'next-entity' });
        mockWebviewView._simulateMessage({ type: 'previous-entity' });
        await flushMicrotasks();

        assert.deepEqual(actions, [
            { type: 'save-field', fieldName: 'role', value: 'Captain' },
            { type: 'reset-field', fieldName: 'role' },
            { type: 'next-entity' },
            { type: 'previous-entity' },
        ]);
    });

    it('clears state and shows idle HTML when close action is received from webview', async () => {
        const actions: any[] = [];
        panel.onAction = async (action: any) => {
            actions.push(action);
        };
        panel.show(makePanelState());

        mockWebviewView._simulateMessage({ type: 'close' });
        await flushMicrotasks();

        // VS Code owns the view lifecycle — close() resets HTML to idle rather than hiding the view
        assert.match(mockWebviewView.webview.html, /idle-message|Start a session|Select a knowledge/);
        assert.equal(panel.getState(), null);
        assert.deepEqual(actions, [{ type: 'close' }]);
    });
});

describe('getKnowledgeReviewPanelHtml', () => {
    it('renders the compact master-detail knowledge review layout in the initial HTML', () => {
        const html = getKnowledgeReviewPanelHtml(makePanelState());

        assert.match(html, /Alice/);
        assert.match(html, /Characters &middot; char:alice/);
        assert.match(html, /Fields/);
        assert.match(html, /Role/);
        assert.match(html, /Alias/);
        // Subtitle uses shorter label (not "Editing override for")
        assert.match(html, /Override for <strong>role<\/strong>/);
        assert.match(html, /Override draft/);
        assert.match(html, /selectField\('role'\)/);
        assert.match(html, /Lead/);
        assert.match(html, /Protagonist/);
        assert.match(html, />Al</);
        assert.equal((html.match(/<textarea/g) || []).length, 1);
        // Conditional layout: review-section and edit-section present instead of comparison tabs
        assert.match(html, /class="review-section"/);
        assert.match(html, /class="edit-section"/);
        assert.doesNotMatch(html, /comparison-tab/);
        // Edit toggle button present
        assert.match(html, /toggleEditMode\(\)/);
    });
});
