/**
 * DiscussionViewProvider — WebviewViewProvider for the Discussion sidebar panel.
 *
 * Replaces DiscussionPanel (WebviewPanel) with a WebviewView that lives in the
 * Secondary Side Bar under the `lit-critic-review` view container.
 *
 * Public surface is identical to DiscussionPanel so callers need no changes:
 *   show(), notifySceneChange(), notifyIndexChange(), clearIndexChangeNotice(),
 *   close(), startDiscuss(), onFindingAction, onDiscussionResult
 *
 * Note: retainContextWhenHidden is set at registration time via
 *   vscode.window.registerWebviewViewProvider(..., { webviewOptions: { retainContextWhenHidden: true } })
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

interface PendingShowState {
    finding: Finding;
    current: number;
    total: number;
    isAmbiguity: boolean;
    discussionTransition?: DiscussionContextTransition;
    readOnlyNotice?: string;
}

export class DiscussionViewProvider implements vscode.WebviewViewProvider, vscode.Disposable {
    private _view: vscode.WebviewView | undefined;
    private _pendingShow: PendingShowState | undefined;
    private abortStream: (() => void) | null = null;
    private streamTimeout: ReturnType<typeof setTimeout> | null = null;

    // Callbacks for the extension to hook into
    onFindingAction: ((action: string, data?: unknown) => void | Promise<void>) | null = null;
    onDiscussionResult: ((result: DiscussResponse) => void) | null = null;

    /**
     * @param getApiClient Lazy getter — resolved only when a discuss message is
     *   sent (i.e. after the server is running). Allows registration at
     *   activate() time before the API client is initialized.
     */
    constructor(private getApiClient: () => ApiClient) {}

    resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken,
    ): void {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
        };

        webviewView.webview.html = this.getIdleHtml();

        webviewView.onDidDispose(() => {
            this._view = undefined;
            this.abortCurrentStream();
        });

        webviewView.webview.onDidReceiveMessage((msg: PanelMessage) => {
            void this.handleMessage(msg);
        });

        // Apply any state that arrived before the view was resolved
        if (this._pendingShow) {
            const p = this._pendingShow;
            this._pendingShow = undefined;
            this.show(p.finding, p.current, p.total, p.isAmbiguity, p.discussionTransition, p.readOnlyNotice);
        }
    }

    /**
     * Show or update the discussion view with a finding.
     */
    show(
        finding: Finding,
        current: number,
        total: number,
        isAmbiguity: boolean,
        discussionTransition?: DiscussionContextTransition,
        readOnlyNotice?: string,
    ): void {
        if (!this._view) {
            // View not yet resolved — queue and open the sidebar container
            this._pendingShow = { finding, current, total, isAmbiguity, discussionTransition, readOnlyNotice };
            void vscode.commands.executeCommand('literaryCritic.discussionView.focus');
            return;
        }

        this._view.webview.html = getDiscussionPanelHtml(
            finding,
            current,
            total,
            isAmbiguity,
            discussionTransition,
            readOnlyNotice,
        );

        if (!this._view.visible) {
            this._view.show(true);
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
     * Reset the view to the idle/empty state.
     * VS Code owns the view lifecycle; we cannot dispose it.
     */
    close(): void {
        this.abortCurrentStream();
        this._pendingShow = undefined;
        if (this._view) {
            this._view.webview.html = this.getIdleHtml();
        }
    }

    dispose(): void {
        this.abortCurrentStream();
    }

    async startDiscuss(message: string): Promise<void> {
        await this.handleDiscuss(message);
    }

    // ------------------------------------------------------------------
    // Message handling
    // ------------------------------------------------------------------

    private async handleMessage(msg: PanelMessage): Promise<void> {
        try {
            switch (msg.type) {
                case 'discuss':
                    if (this.onFindingAction) {
                        await this.onFindingAction('discuss', msg.message);
                    } else {
                        await this.handleDiscuss(msg.message);
                    }
                    break;
                case 'accept':
                    await this.onFindingAction?.('accept');
                    break;
                case 'reject':
                    await this.onFindingAction?.('reject', msg.reason);
                    break;
                case 'continue':
                    await this.onFindingAction?.('continue');
                    break;
                case 'reviewFinding':
                    await this.onFindingAction?.('reviewFinding');
                    break;
                case 'ambiguity':
                    await this.onFindingAction?.('ambiguity', msg.intentional);
                    break;
                case 'rerunAnalysis':
                    await this.onFindingAction?.('rerunAnalysis');
                    break;
                case 'dismissIndexChange':
                    await this.onFindingAction?.('dismissIndexChange');
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

        this.abortStream = this.getApiClient().streamDiscuss(
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
        this._view?.webview.postMessage(msg);
    }

    private getIdleHtml(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-editor-foreground);
    background: var(--vscode-editor-background);
    padding: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
    margin: 0;
    box-sizing: border-box;
}
.idle-message {
    text-align: center;
    opacity: 0.6;
    font-style: italic;
}
</style>
</head>
<body>
<div class="idle-message">Start a session to see findings here.</div>
</body>
</html>`;
    }
}
