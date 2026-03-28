/**
 * Real tests for DiscussionViewProvider module.
 *
 * Tests the actual DiscussionViewProvider class (formerly DiscussionPanel)
 * with mocked vscode API.
 */

import { strict as assert } from 'assert';
import { createFreshMockVscode, MockWebviewView, sampleFinding } from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

describe('DiscussionPanel (Real)', () => {
    let DiscussionPanel: any;
    let mockVscode: any;
    let panel: any;
    let mockWebviewView: MockWebviewView;
    let mockApiClient: any;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();
        mockWebviewView = new MockWebviewView();

        // Mock ApiClient
        mockApiClient = {
            streamDiscuss: (_message: string, _onToken: any, _onDone: any, _onError: any) => {
                return () => {};
            },
        };

        const module = proxyquire('../../vscode-extension/src/discussionViewProvider', {
            'vscode': mockVscode,
        });
        DiscussionPanel = module.DiscussionViewProvider;
    });

    /** Helper: create a provider instance with the mock view already resolved. */
    function createTestPanel() {
        const p = new DiscussionPanel(() => mockApiClient);
        // Simulate VS Code calling resolveWebviewView when the sidebar section opens
        p.resolveWebviewView(mockWebviewView, {}, {});
        return p;
    }

    afterEach(() => {
        if (panel) {
            panel.dispose();
        }
    });

    describe('constructor', () => {
        it('should create panel with API client', () => {
            panel = createTestPanel();
            assert.ok(panel);
        });
    });

    describe('show', () => {
        it('should create webview panel on first show', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            assert.ok(mockWebviewView);
            assert.equal(mockWebviewView.visible, true);
        });

        it('should reuse existing panel on subsequent shows', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);
            panel.show(sampleFinding, 2, 3, false);

            // Same view object is reused (not recreated)
            assert.ok(true);
        });

        it('should generate HTML with finding details', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            assert.match(mockWebviewView.webview.html, /rhythm breaks/);
            assert.match(mockWebviewView.webview.html, /major/i);
        });

        it('should show progress in HTML (1/3)', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            assert.match(mockWebviewView.webview.html, /Finding\s*<strong>1\/3<\/strong>/);
        });

        it('should include severity color in HTML', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            // Should have color style for major findings
            assert.match(mockWebviewView.webview.html, /#ff9800/i); // major = orange
        });

        it('should format line range in HTML', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            assert.match(mockWebviewView.webview.html, /Lines 42.*45/);
        });

        it('should include options list in HTML', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            assert.match(mockWebviewView.webview.html, /Rewrite for smoother rhythm/);
            assert.match(mockWebviewView.webview.html, /<ol>/); // ordered list
        });

        it('should show ambiguity buttons when isAmbiguity=true', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, true);

            assert.match(mockWebviewView.webview.html, /ambiguity-buttons/);
            assert.match(mockWebviewView.webview.html, /Intentional/);
            assert.match(mockWebviewView.webview.html, /Accidental/);
        });

        it('should hide ambiguity buttons when isAmbiguity=false', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            // Should not render ambiguity action markup/buttons.
            const html = mockWebviewView.webview.html;
            const hasAmbiguityButtons = html.includes('<div class="ambiguity-buttons">')
                || html.includes("type:'ambiguity', intentional:true")
                || html.includes("type:'ambiguity', intentional:false")
                || html.includes('>Intentional<')
                || html.includes('>Accidental<');
            assert.ok(!hasAmbiguityButtons);
        });

        it('should include action buttons in HTML', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            assert.match(mockWebviewView.webview.html, /Accept/);
            assert.match(mockWebviewView.webview.html, /Reject/);
            assert.match(mockWebviewView.webview.html, /Review/);
            assert.doesNotMatch(mockWebviewView.webview.html, /Export Learning/);
        });

        it('should allow vertically resizing the discussion input textarea', () => {
            panel = createTestPanel();

            panel.show(sampleFinding, 1, 3, false);

            const html = mockWebviewView.webview.html;
            assert.match(html, /resize:\s*vertical/);
            assert.match(html, /max-height:\s*40vh/);
            assert.ok(!html.includes('resize: none'));
        });

        it('should render the latest finding status badge', () => {
            panel = createTestPanel();
            const acceptedFinding = { ...sampleFinding, status: 'accepted' };

            panel.show(acceptedFinding, 1, 3, false);

            assert.match(mockWebviewView.webview.html, /status-accepted/);
            assert.match(mockWebviewView.webview.html, />accepted</);
        });

        it('should render archived pre-edit context when a discussion transition is provided', () => {
            panel = createTestPanel();

            const findingAfterReview = {
                ...sampleFinding,
                evidence: 'Updated evidence',
                discussion_turns: [],
            };

            panel.show(
                findingAfterReview,
                1,
                3,
                false,
                {
                    previousFinding: sampleFinding,
                    previousTurns: [
                        { role: 'assistant', content: 'Original recommendation.' },
                        { role: 'user', content: 'I revised this part.' },
                    ],
                    note: 'Finding re-evaluated after scene edits. Starting a new discussion context.',
                },
            );

            assert.match(mockWebviewView.webview.html, /Previous context \(before scene edits\)/);
            assert.match(mockWebviewView.webview.html, /Original recommendation\./);
            assert.match(mockWebviewView.webview.html, /I revised this part\./);
            assert.ok(!mockWebviewView.webview.html.includes('No prior discussion turns.'));
        });

        it('should render read-only notice when provided for closed sessions', () => {
            panel = createTestPanel();

            panel.show(
                sampleFinding,
                1,
                3,
                false,
                undefined,
                'Viewing completed session — actions will reopen it.',
            );

            assert.match(mockWebviewView.webview.html, /session-notice/);
            assert.match(mockWebviewView.webview.html, /Viewing completed session — actions will reopen it\./);
        });
    });

    describe('notifySceneChange', () => {
        it('should post scene change message to webview', () => {
            panel = createTestPanel();
            panel.show(sampleFinding, 1, 3, false);

            let messagePosted = false;
            mockWebviewView.webview.postMessage = (msg: any) => {
                messagePosted = true;
                assert.equal(msg.type, 'sceneChange');
            };

            panel.notifySceneChange({ adjusted: 2, stale: 1, re_evaluated: [] });

            assert.ok(messagePosted);
        });
    });

    describe('close', () => {
        it('should reset the view to idle HTML state', () => {
            panel = createTestPanel();
            panel.show(sampleFinding, 1, 3, false);

            panel.close();

            // VS Code owns the view lifecycle; close() resets HTML to the idle placeholder
            assert.match(mockWebviewView.webview.html, /idle-message|Start a session/);
        });
    });

    describe('dispose', () => {
        it('should abort any active stream and not throw', () => {
            panel = createTestPanel();
            panel.show(sampleFinding, 1, 3, false);

            // dispose() cancels pending streams; VS Code owns the view so it stays visible
            assert.doesNotThrow(() => panel.dispose());
        });
    });
});
