/**
 * Discussion Panel — Webview panel for interactive discussion about a finding.
 *
 * Opens as a VS Code Webview panel showing:
 *   - Current finding details (severity, lens, location, evidence, impact, options)
 *   - Chat-style interface for discussion with the critic
 *   - Streaming responses via SSE
 *   - Action buttons: Accept, Reject, Continue, Skip Minor
 *   - Ambiguity buttons for ambiguity findings
 */

import * as vscode from 'vscode';
import { ApiClient } from './apiClient';
import { Finding, DiscussResponse } from './types';

type PanelMessage =
    | { type: 'discuss'; message: string }
    | { type: 'accept' }
    | { type: 'reject'; reason: string }
    | { type: 'continue' }
    | { type: 'skipMinor' }
    | { type: 'ambiguity'; intentional: boolean }
    | { type: 'saveSession' }
    | { type: 'saveLearning' };

export class DiscussionPanel implements vscode.Disposable {
    private panel: vscode.WebviewPanel | null = null;
    private apiClient: ApiClient;
    private abortStream: (() => void) | null = null;
    private streamTimeout: ReturnType<typeof setTimeout> | null = null;

    // Callbacks for the extension to hook into
    onFindingAction: ((action: string, data?: unknown) => void) | null = null;

    constructor(apiClient: ApiClient) {
        this.apiClient = apiClient;
    }

    /**
     * Show or update the discussion panel with a finding.
     */
    show(finding: Finding, current: number, total: number, isAmbiguity: boolean): void {
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

        this.panel.webview.html = this.getHtml(finding, current, total, isAmbiguity);

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
                case 'skipMinor':
                    this.onFindingAction?.('skipMinor');
                    break;
                case 'ambiguity':
                    this.onFindingAction?.('ambiguity', msg.intentional);
                    break;
                case 'saveSession':
                    this.onFindingAction?.('saveSession');
                    break;
                case 'saveLearning':
                    this.onFindingAction?.('saveLearning');
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

    // ------------------------------------------------------------------
    // Webview HTML
    // ------------------------------------------------------------------

    private getHtml(finding: Finding, current: number, total: number, isAmbiguity: boolean): string {
        const severityColor: Record<string, string> = {
            'critical': '#f44336',
            'major': '#ff9800',
            'minor': '#2196f3',
        };
        const color = severityColor[finding.severity] || '#ff9800';

        const lineRange = finding.line_start !== null
            ? finding.line_end !== null && finding.line_end !== finding.line_start
                ? `Lines ${finding.line_start}–${finding.line_end}`
                : `Line ${finding.line_start}`
            : finding.location;

        const optionsHtml = finding.options.length > 0
            ? `<div class="options"><strong>Suggestions:</strong><ol>${finding.options.map(o => `<li>${escapeHtml(o)}</li>`).join('')}</ol></div>`
            : '';

        const ambiguityButtons = isAmbiguity
            ? `<div class="ambiguity-buttons">
                <button onclick="send({type:'ambiguity', intentional:true})" class="btn btn-info">Intentional</button>
                <button onclick="send({type:'ambiguity', intentional:false})" class="btn btn-warning">Accidental</button>
               </div>`
            : '';

        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    :root {
        --bg: var(--vscode-editor-background);
        --fg: var(--vscode-editor-foreground);
        --border: var(--vscode-panel-border);
        --input-bg: var(--vscode-input-background);
        --input-fg: var(--vscode-input-foreground);
        --input-border: var(--vscode-input-border);
        --button-bg: var(--vscode-button-background);
        --button-fg: var(--vscode-button-foreground);
        --button-hover: var(--vscode-button-hoverBackground);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: var(--vscode-font-family);
        font-size: var(--vscode-font-size);
        color: var(--fg);
        background: var(--bg);
        padding: 12px;
        display: flex;
        flex-direction: column;
        height: 100vh;
    }

    /* Finding header */
    .finding-header {
        border-left: 4px solid ${color};
        padding: 8px 12px;
        margin-bottom: 12px;
        background: var(--vscode-textBlockQuote-background);
        border-radius: 2px;
        max-height: 40vh;
        overflow-y: auto;
        flex-shrink: 0;
    }
    .finding-header .meta {
        font-size: 0.85em;
        opacity: 0.8;
        margin-bottom: 4px;
    }
    .finding-header .severity {
        color: ${color};
        font-weight: bold;
        text-transform: uppercase;
    }
    .finding-header .evidence {
        margin: 8px 0;
        line-height: 1.5;
    }
    .finding-header .impact {
        font-style: italic;
        opacity: 0.9;
        margin-top: 6px;
    }
    .options { margin-top: 8px; }
    .options ol { padding-left: 20px; margin-top: 4px; }
    .options li { margin-bottom: 2px; }

    /* Chat area */
    .chat {
        flex: 1;
        min-height: 120px;
        overflow-y: auto;
        margin: 8px 0;
        padding: 4px;
    }
    .message {
        margin-bottom: 10px;
        padding: 8px 10px;
        border-radius: 6px;
        max-width: 90%;
        line-height: 1.5;
        white-space: pre-wrap;
    }
    .message.user {
        background: var(--vscode-textBlockQuote-background);
        margin-left: auto;
        text-align: right;
    }
    .message.assistant {
        background: var(--vscode-editor-inactiveSelectionBackground);
    }
    .message.system {
        background: transparent;
        opacity: 0.7;
        font-style: italic;
        font-size: 0.9em;
        text-align: center;
        max-width: 100%;
    }
    .streaming-cursor::after {
        content: '▊';
        animation: blink 1s infinite;
    }
    @keyframes blink {
        50% { opacity: 0; }
    }

    /* Input area */
    .input-area {
        display: flex;
        gap: 6px;
        margin-top: 8px;
        flex-shrink: 0;
    }
    .input-area textarea {
        flex: 1;
        background: var(--input-bg);
        color: var(--input-fg);
        border: 1px solid var(--input-border);
        border-radius: 4px;
        padding: 6px 8px;
        font-family: inherit;
        font-size: inherit;
        resize: none;
        min-height: 36px;
        max-height: 120px;
    }
    .input-area textarea:focus {
        outline: 1px solid var(--vscode-focusBorder);
    }

    /* Buttons */
    .btn {
        padding: 4px 12px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-family: inherit;
        font-size: 0.9em;
        background: var(--button-bg);
        color: var(--button-fg);
    }
    .btn:hover { background: var(--button-hover); }
    .btn-success { background: #4caf50; color: white; }
    .btn-danger { background: #f44336; color: white; }
    .btn-info { background: #2196f3; color: white; }
    .btn-warning { background: #ff9800; color: white; }
    .btn-secondary {
        background: var(--vscode-button-secondaryBackground);
        color: var(--vscode-button-secondaryForeground);
    }

    .action-buttons {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        margin-top: 8px;
        flex-shrink: 0;
    }
    .ambiguity-buttons {
        display: flex;
        gap: 6px;
        margin-top: 8px;
        flex-shrink: 0;
    }
    .progress {
        font-size: 0.85em;
        opacity: 0.7;
        text-align: center;
        margin-top: 4px;
        flex-shrink: 0;
    }
</style>
</head>
<body>
    <div class="finding-header">
        <div class="meta">
            Finding <strong>${current}/${total}</strong> •
            <span class="severity">${escapeHtml(finding.severity)}</span> •
            ${escapeHtml(finding.lens)} •
            ${escapeHtml(lineRange)}
        </div>
        <div class="evidence">${escapeHtml(finding.evidence)}</div>
        ${finding.impact ? `<div class="impact">${escapeHtml(finding.impact)}</div>` : ''}
        ${optionsHtml}
    </div>

    ${ambiguityButtons}

    <div class="chat" id="chat"></div>

    <div class="input-area">
        <textarea id="input" placeholder="Discuss this finding..." rows="2"
            onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
        <button class="btn" onclick="sendMessage()">Send</button>
    </div>

    <div class="action-buttons">
        <button class="btn btn-success" onclick="send({type:'accept'})">✓ Accept</button>
        <button class="btn btn-danger" onclick="rejectWithReason()">✗ Reject</button>
        <button class="btn btn-secondary" onclick="send({type:'continue'})">Next →</button>
        <button class="btn btn-secondary" onclick="send({type:'skipMinor'})">Skip Minor</button>
        <button class="btn btn-secondary" onclick="send({type:'saveSession'})">Save Session</button>
    </div>

    <div class="progress">Finding ${current} of ${total}</div>

<script>
    const vscode = acquireVsCodeApi();
    const chat = document.getElementById('chat');
    const input = document.getElementById('input');
    let streamingEl = null;

    function send(msg) {
        vscode.postMessage(msg);
    }

    function sendMessage() {
        const text = input.value.trim();
        if (!text) return;
        input.value = '';
        send({ type: 'discuss', message: text });
    }

    function rejectWithReason() {
        const reason = input.value.trim();
        send({ type: 'reject', reason: reason || '' });
    }

    function addMessage(role, text) {
        const div = document.createElement('div');
        div.className = 'message ' + role;
        div.textContent = text;
        chat.appendChild(div);
        chat.scrollTop = chat.scrollHeight;
        return div;
    }

    function escapeText(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    window.addEventListener('message', event => {
        const msg = event.data;
        switch (msg.type) {
            case 'userMessage':
                addMessage('user', msg.text);
                break;

            case 'streamStart':
                streamingEl = addMessage('assistant', '');
                streamingEl.classList.add('streaming-cursor');
                break;

            case 'streamToken':
                if (streamingEl) {
                    streamingEl.textContent += msg.text;
                    chat.scrollTop = chat.scrollHeight;
                }
                break;

            case 'streamDone':
                if (streamingEl) {
                    // If no tokens were streamed, the assistant bubble is empty.
                    // Populate it with the response text from the done event
                    // (covers error messages and non-streamed responses).
                    if (!streamingEl.textContent && msg.result && msg.result.response) {
                        streamingEl.textContent = msg.result.response;
                    }
                    streamingEl.classList.remove('streaming-cursor');
                    streamingEl = null;
                }
                // Show explicit error from done event (e.g. "No active finding")
                if (msg.result && msg.result.error) {
                    addMessage('system', 'Error: ' + msg.result.error);
                }
                if (msg.result && msg.result.status) {
                    const status = msg.result.status;
                    if (status !== 'continue') {
                        addMessage('system', 'Status: ' + status);
                    }
                    if (msg.result.finding) {
                        addMessage('system', 'Finding updated (see diagnostics).');
                    }
                }
                break;

            case 'streamError':
                if (streamingEl) {
                    streamingEl.classList.remove('streaming-cursor');
                    streamingEl = null;
                }
                addMessage('system', 'Error: ' + msg.error);
                break;

            case 'sceneChange':
                let text = '📝 Scene change detected!';
                if (msg.adjusted) text += '\\n   Adjusted: ' + msg.adjusted + ' findings';
                if (msg.stale) text += '\\n   Stale: ' + msg.stale + ' findings';
                if (msg.reEvaluated && msg.reEvaluated.length > 0) {
                    for (const r of msg.reEvaluated) {
                        text += '\\n   Re-evaluated: Finding #' + r.finding_number + ' → ' + r.status;
                    }
                }
                addMessage('system', text);
                break;
        }
    });

    // Scroll to top to show finding header, then focus input
    window.scrollTo(0, 0);
    input.focus();
</script>
</body>
</html>`;
    }
}

/** Escape HTML entities for safe insertion. */
function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
