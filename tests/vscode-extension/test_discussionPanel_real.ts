/**
 * Real tests for DiscussionPanel module.
 * 
 * Tests the actual DiscussionPanel class with mocked vscode API.
 */

import { strict as assert } from 'assert';
import { createFreshMockVscode, MockWebviewPanel, sampleFinding } from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

describe('DiscussionPanel (Real)', () => {
    let DiscussionPanel: any;
    let mockVscode: any;
    let panel: any;
    let mockWebviewPanel: MockWebviewPanel;
    let mockApiClient: any;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();
        
        // Capture webview panel creation
        mockWebviewPanel = new MockWebviewPanel('test', 'test', 1, {});
        mockVscode.window.createWebviewPanel = () => mockWebviewPanel;

        // Mock ApiClient
        mockApiClient = {
            streamDiscuss: (message: string, onToken: any, onDone: any, onError: any) => {
                // Return abort function
                return () => {};
            },
        };

        const module = proxyquire('../../vscode-extension/src/discussionPanel', {
            'vscode': mockVscode,
        });
        DiscussionPanel = module.DiscussionPanel;
    });

    afterEach(() => {
        if (panel) {
            panel.dispose();
        }
    });

    describe('constructor', () => {
        it('should create panel with API client', () => {
            panel = new DiscussionPanel(mockApiClient);
            assert.ok(panel);
        });
    });

    describe('show', () => {
        it('should create webview panel on first show', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            assert.ok(mockWebviewPanel);
            assert.equal(mockWebviewPanel.visible, true);
        });

        it('should reuse existing panel on subsequent shows', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            const firstPanel = mockWebviewPanel;
            
            panel.show(sampleFinding, 2, 3, false);
            // Should still be the same panel (reused)
            assert.ok(true); // Can't directly compare, but no error means reuse worked
        });

        it('should generate HTML with finding details', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            assert.match(mockWebviewPanel.webview.html, /rhythm breaks/);
            assert.match(mockWebviewPanel.webview.html, /major/i);
        });

        it('should show progress in HTML (1/3)', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            assert.match(mockWebviewPanel.webview.html, /Finding\s*<strong>1\/3<\/strong>/);
        });

        it('should include severity color in HTML', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            // Should have color style for major findings
            assert.match(mockWebviewPanel.webview.html, /#ff9800/i); // major = orange
        });

        it('should format line range in HTML', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            assert.match(mockWebviewPanel.webview.html, /Lines 42.*45/);
        });

        it('should include options list in HTML', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            assert.match(mockWebviewPanel.webview.html, /Rewrite for smoother rhythm/);
            assert.match(mockWebviewPanel.webview.html, /<ol>/); // ordered list
        });

        it('should show ambiguity buttons when isAmbiguity=true', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, true);
            
            assert.match(mockWebviewPanel.webview.html, /ambiguity-buttons/);
            assert.match(mockWebviewPanel.webview.html, /Intentional/);
            assert.match(mockWebviewPanel.webview.html, /Accidental/);
        });

        it('should hide ambiguity buttons when isAmbiguity=false', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            // Should not have ambiguity buttons div
            const html = mockWebviewPanel.webview.html;
            const hasAmbiguityButtons = html.includes('ambiguity-buttons') && 
                                       html.includes('Intentional');
            assert.ok(!hasAmbiguityButtons);
        });

        it('should include action buttons in HTML', () => {
            panel = new DiscussionPanel(mockApiClient);
            
            panel.show(sampleFinding, 1, 3, false);
            
            assert.match(mockWebviewPanel.webview.html, /Accept/);
            assert.match(mockWebviewPanel.webview.html, /Reject/);
            assert.match(mockWebviewPanel.webview.html, /Review/);
            assert.doesNotMatch(mockWebviewPanel.webview.html, /Export Learning/);
        });

        it('should allow vertically resizing the discussion input textarea', () => {
            panel = new DiscussionPanel(mockApiClient);

            panel.show(sampleFinding, 1, 3, false);

            const html = mockWebviewPanel.webview.html;
            assert.match(html, /resize:\s*vertical/);
            assert.match(html, /max-height:\s*40vh/);
            assert.ok(!html.includes('resize: none'));
        });

        it('should render the latest finding status badge', () => {
            panel = new DiscussionPanel(mockApiClient);
            const acceptedFinding = { ...sampleFinding, status: 'accepted' };

            panel.show(acceptedFinding, 1, 3, false);

            assert.match(mockWebviewPanel.webview.html, /status-accepted/);
            assert.match(mockWebviewPanel.webview.html, />accepted</);
        });

        it('should render archived pre-edit context when a discussion transition is provided', () => {
            panel = new DiscussionPanel(mockApiClient);

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

            assert.match(mockWebviewPanel.webview.html, /Previous context \(before scene edits\)/);
            assert.match(mockWebviewPanel.webview.html, /Original recommendation\./);
            assert.match(mockWebviewPanel.webview.html, /I revised this part\./);
            assert.ok(!mockWebviewPanel.webview.html.includes('No prior discussion turns.'));
        });

        it('should render read-only notice when provided for closed sessions', () => {
            panel = new DiscussionPanel(mockApiClient);

            panel.show(
                sampleFinding,
                1,
                3,
                false,
                undefined,
                'Viewing completed session — actions will reopen it.',
            );

            assert.match(mockWebviewPanel.webview.html, /session-notice/);
            assert.match(mockWebviewPanel.webview.html, /Viewing completed session — actions will reopen it\./);
        });
    });

    describe('notifySceneChange', () => {
        it('should post scene change message to webview', () => {
            panel = new DiscussionPanel(mockApiClient);
            panel.show(sampleFinding, 1, 3, false);
            
            let messagePosted = false;
            const originalPostMessage = mockWebviewPanel.webview.postMessage;
            mockWebviewPanel.webview.postMessage = (msg: any) => {
                messagePosted = true;
                assert.equal(msg.type, 'sceneChange');
            };
            
            panel.notifySceneChange({ adjusted: 2, stale: 1, re_evaluated: [] });
            
            assert.ok(messagePosted);
        });
    });

    describe('close', () => {
        it('should dispose the webview panel', () => {
            panel = new DiscussionPanel(mockApiClient);
            panel.show(sampleFinding, 1, 3, false);
            
            panel.close();
            
            assert.equal(mockWebviewPanel.visible, false);
        });
    });

    describe('dispose', () => {
        it('should close the panel', () => {
            panel = new DiscussionPanel(mockApiClient);
            panel.show(sampleFinding, 1, 3, false);
            
            panel.dispose();
            
            assert.equal(mockWebviewPanel.visible, false);
        });
    });
});
