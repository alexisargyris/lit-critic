/**
 * Discussion Panel — Webview panel for interactive discussion about a finding.
 *
 * Opens as a VS Code Webview panel showing:
 *   - Current finding details (severity, lens, location, evidence, impact, options)
 *   - Chat-style interface for discussion with the critic
 *   - Streaming responses via SSE
 *   - Action buttons: Accept, Reject, Review
 *   - Ambiguity buttons for ambiguity findings
 */

import * as vscode from 'vscode';
import { ApiClient } from './apiClient';
import { Finding, DiscussResponse, DiscussionContextTransition, IndexChangeReport } from './types';
import { getDiscussionPanelHtml } from './ui/discussionPanelView';

type PanelMessage =
    | { type: 'discuss'; message: string }
    | { type: 'accept' }
    | { type: 'reject'; reason: string }
    | { type: 'continue' }
    | { type: 'reviewFinding' }
    | { type: 'ambiguity'; intentional: boolean }
    | { type: 'rerunAnalysis' }
    | { type: 'dismissIndexChange' };

export class DiscussionPanel implements vscode.Disposable {
    private panel: vscode.WebviewPanel | null = null;
    private apiClient: ApiClient;
    private abortStream: (() => void) | null = null;
    private streamTimeout: ReturnType<typeof setTimeout> | null = null;

    // Callbacks for the extension to hook into
    onFindingAction: ((action: string, data?: unknown) => void) | null = null;
    onDiscussionResult: ((result: DiscussResponse) => void) | null = null;

    constructor(apiClient: ApiClient) {
        this.apiClient = apiClient;
    }

    /**
     * Show or update the discussion panel with a finding.
     */
    show(
        finding: Finding,
        current: number,
        total: number,
        isAmbiguity: boolean,
        discussionTransition?: DiscussionContextTransition,
        readOnlyNotice?: string,
    ): void {
        if (!this.panel) {
            this.panel = vscode.window.createWebviewPanel(
                'literaryCriticDiscussion',
                'lit-critic — Discussion',
                vscode.ViewColumn.Beside,
                {
                    enableScripts: true,
                    retainContextWhenHidden: true,
                }
            );

            this.panel.onDidDispose(() => {
                this.panel = null;
                this.abortCurrentStream();
            });

            this.panel.webview.onDidReceiveMessage((msg: PanelMessage) => {
                this.handleMessage(msg);
            });
        }

        this.panel.webview.html = getDiscussionPanelHtml(
            finding,
            current,
            total,
            isAmbiguity,
            discussionTransition,
            readOnlyNotice,
        );

        // Only reveal if the panel isn't already showing — calling reveal()
        // every time causes VS Code to re-layout editors (looks like the
        // scene file is being re-opened).
        // Use the panel's current column (where it already lives) instead of
        // ViewColumn.Beside, which would create a new group relative to the
        // active editor (ambiguous when clicking from the sidebar tree).
        if (!this.panel.visible) {
            this.panel.reveal(this.panel.viewColumn || vscode.ViewColumn.Two, true);
        }
    }

    /**
     * Append a scene change notification to the chat.
     */
    notifySceneChange(report: { adjusted: number; stale: number; re_evaluated: Array<{ finding_number: number; status: string }> }): void {
        this.postMessage({
            type: 'sceneChange',
            adjusted: report.adjusted,
            stale: report.stale,
            reEvaluated: report.re_evaluated,
        });
    }

    notifyIndexChange(report: IndexChangeReport): void {
        this.postMessage({
            type: 'indexChange',
            report,
        });
    }

    clearIndexChangeNotice(): void {
        this.postMessage({ type: 'indexChangeClear' });
    }

    /**
     * Close the panel.
     */
    close(): void {
        this.abortCurrentStream();
        this.panel?.dispose();
        this.panel = null;
    }

    dispose(): void {
        this.close();
    }

    // ------------------------------------------------------------------
    // Message handling
    // ------------------------------------------------------------------

    private async handleMessage(msg: PanelMessage): Promise<void> {
        try {
            switch (msg.type) {
                case 'discuss':
                    await this.handleDiscuss(msg.message);
                    break;
                case 'accept':
                    this.onFindingAction?.('accept');
                    break;
                case 'reject':
                    this.onFindingAction?.('reject', msg.reason);
                    break;
                case 'continue':
                    this.onFindingAction?.('continue');
                    break;
                case 'reviewFinding':
                    this.onFindingAction?.('reviewFinding');
                    break;
                case 'ambiguity':
                    this.onFindingAction?.('ambiguity', msg.intentional);
                    break;
                case 'rerunAnalysis':
                    this.onFindingAction?.('rerunAnalysis');
                    break;
                case 'dismissIndexChange':
                    this.onFindingAction?.('dismissIndexChange');
                    break;
            }
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`lit-critic: ${message}`);
        }
    }

    private async handleDiscuss(message: string): Promise<void> {
        this.abortCurrentStream();

        // Show user message immediately
        this.postMessage({ type: 'userMessage', text: message });
        this.postMessage({ type: 'streamStart' });

        let streamFinished = false;

        const markFinished = () => {
            streamFinished = true;
            if (this.streamTimeout) {
                clearTimeout(this.streamTimeout);
                this.streamTimeout = null;
            }
        };

        this.abortStream = this.apiClient.streamDiscuss(
            message,
            (token: string) => {
                this.postMessage({ type: 'streamToken', text: token });
            },
            (result: DiscussResponse) => {
                markFinished();
                this.onDiscussionResult?.(result);
                this.postMessage({ type: 'streamDone', result });
                this.abortStream = null;
            },
            (err: Error) => {
                markFinished();
                this.postMessage({ type: 'streamError', error: err.message });
                this.abortStream = null;
            },
            (report) => {
                // Scene change detected during discussion — notify the webview
                this.postMessage({
                    type: 'sceneChange',
                    adjusted: report.adjusted,
                    stale: report.stale,
                    reEvaluated: report.re_evaluated,
                });
            },
        );

        // Safety timeout — if neither done nor error arrives within 5 minutes,
        // stop the spinner so the user isn't left staring at a blinking cursor.
        this.streamTimeout = setTimeout(() => {
            if (!streamFinished) {
                this.postMessage({ type: 'streamError', error: 'Response timed out.' });
                this.abortCurrentStream();
            }
        }, 300_000);
    }

    private abortCurrentStream(): void {
        if (this.streamTimeout) {
            clearTimeout(this.streamTimeout);
            this.streamTimeout = null;
        }
        if (this.abortStream) {
            this.abortStream();
            this.abortStream = null;
        }
    }

    private postMessage(msg: Record<string, unknown>): void {
        this.panel?.webview.postMessage(msg);
    }
}

