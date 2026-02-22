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

        this.panel.webview.html = this.getHtml(
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

    // ------------------------------------------------------------------
    // Webview HTML
    // ------------------------------------------------------------------

    private getHtml(
        finding: Finding,
        current: number,
        total: number,
        isAmbiguity: boolean,
        discussionTransition?: DiscussionContextTransition,
        readOnlyNotice?: string,
    ): string {
        const severityColor: Record<string, string> = {
            'critical': '#f44336',
            'major': '#ff9800',
            'minor': '#2196f3',
        };
        const color = severityColor[finding.severity] || '#ff9800';

        const formatLineRange = (f: Pick<Finding, 'line_start' | 'line_end' | 'location'>): string => (
            f.line_start !== null
                ? f.line_end !== null && f.line_end !== f.line_start
                    ? `Lines ${f.line_start}–${f.line_end}`
                    : `Line ${f.line_start}`
                : f.location
        );

        const lineRange = formatLineRange(finding);

        const optionsHtml = finding.options.length > 0
            ? `<div class="options"><strong>Suggestions:</strong><ol>${finding.options.map(o => `<li>${escapeHtml(o)}</li>`).join('')}</ol></div>`
            : '';

        const statusLabel = (finding.status || 'pending').toLowerCase();
        const statusHtml = `<span class="status-badge status-${escapeHtml(statusLabel)}">${escapeHtml(statusLabel)}</span>`;

        const ambiguityButtons = isAmbiguity
            ? `<div class="ambiguity-buttons">
                <button onclick="send({type:'ambiguity', intentional:true})" class="btn btn-info">Intentional</button>
                <button onclick="send({type:'ambiguity', intentional:false})" class="btn btn-warning">Accidental</button>
               </div>`
            : '';

        const currentTurns = discussionTransition ? [] : (finding.discussion_turns || []);
        const initialTurns = currentTurns.map((turn) => {
            const role = (turn.role || '').toLowerCase();
            if (role === 'user') {
                return { roleClass: 'user', label: 'You', content: turn.content || '' };
            }
            if (role === 'assistant') {
                return { roleClass: 'assistant', label: 'Critic', content: turn.content || '' };
            }
            return { roleClass: 'system', label: 'System', content: turn.content || '' };
        });

        const initialTurnsHtml = initialTurns.map((t) =>
            `<div class="message ${t.roleClass}">${escapeHtml(t.content)}</div>`
        ).join('');

        const transitionTurns = (discussionTransition?.previousTurns || []).map((turn) => {
            const role = (turn.role || '').toLowerCase();
            if (role === 'user') {
                return { roleClass: 'user', content: turn.content || '' };
            }
            if (role === 'assistant') {
                return { roleClass: 'assistant', content: turn.content || '' };
            }
            return { roleClass: 'system', content: turn.content || '' };
        });

        const transitionTurnsHtml = transitionTurns.length > 0
            ? transitionTurns.map((t) =>
                `<div class="message ${t.roleClass}">${escapeHtml(t.content)}</div>`
            ).join('')
            : '<div class="message system">No prior discussion turns.</div>';

        const transitionHtml = discussionTransition
            ? `<div class="history-block">
                <div class="history-title">Previous context (before scene edits)</div>
                <div class="history-meta">
                    <span class="severity">${escapeHtml(discussionTransition.previousFinding.severity)}</span> •
                    ${escapeHtml(discussionTransition.previousFinding.lens)} •
                    ${escapeHtml(formatLineRange(discussionTransition.previousFinding))}
                </div>
                <div class="history-evidence">${escapeHtml(discussionTransition.previousFinding.evidence)}</div>
                <div class="history-thread">${transitionTurnsHtml}</div>
            </div>
            <div class="message system">📝 ${escapeHtml(
                discussionTransition.note || 'Finding re-evaluated after scene edits. Starting a new discussion context.'
            )}</div>`
            : '';

        const noticeHtml = readOnlyNotice
            ? `<div class="session-notice">${escapeHtml(readOnlyNotice)}</div>`
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
    .finding-header .status-badge {
        display: inline-block;
        margin-left: 6px;
        padding: 1px 6px;
        border-radius: 10px;
        border: 1px solid var(--border);
        text-transform: uppercase;
        font-size: 0.78em;
        letter-spacing: 0.04em;
        opacity: 0.95;
    }
    .finding-header .status-pending { opacity: 0.7; }
    .finding-header .status-accepted { color: #4caf50; border-color: #4caf50; }
    .finding-header .status-rejected { color: #f44336; border-color: #f44336; }
    .finding-header .status-withdrawn { color: #9e9e9e; border-color: #9e9e9e; }
    .finding-header .status-revised { color: #2196f3; border-color: #2196f3; }
    .finding-header .status-escalated { color: #ff9800; border-color: #ff9800; }
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
    .history-block {
        border: 1px dashed var(--border);
        border-radius: 6px;
        padding: 8px;
        margin-bottom: 10px;
        background: color-mix(in srgb, var(--bg) 70%, var(--vscode-textBlockQuote-background) 30%);
    }
    .history-title {
        font-size: 0.82em;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.8;
        margin-bottom: 4px;
    }
    .history-meta {
        font-size: 0.82em;
        opacity: 0.8;
        margin-bottom: 4px;
    }
    .history-evidence {
        font-size: 0.9em;
        margin-bottom: 8px;
        line-height: 1.4;
    }
    .history-thread {
        border-top: 1px dashed var(--border);
        padding-top: 8px;
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
        align-items: flex-end;
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
        resize: vertical;
        min-height: 36px;
        max-height: 40vh;
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
    .session-notice {
        border: 1px solid var(--vscode-editorInfo-foreground);
        background: color-mix(in srgb, var(--vscode-editorInfo-foreground) 12%, transparent);
        color: var(--vscode-editorInfo-foreground);
        border-radius: 4px;
        padding: 8px 10px;
        margin-bottom: 8px;
        font-size: 0.9em;
        flex-shrink: 0;
    }
    .index-change-notice {
        border: 1px solid var(--vscode-editorWarning-foreground);
        background: color-mix(in srgb, var(--vscode-editorWarning-foreground) 12%, transparent);
        color: var(--vscode-editorWarning-foreground);
        border-radius: 4px;
        padding: 8px 10px;
        margin-bottom: 8px;
        font-size: 0.9em;
        flex-shrink: 0;
        display: none;
    }
    .index-change-notice.visible {
        display: block;
    }
    .index-change-actions {
        margin-top: 8px;
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
    }
</style>
</head>
<body>
    ${noticeHtml}
    <div id="indexChangeNotice" class="index-change-notice">
        <div id="indexChangeText"></div>
        <div class="index-change-actions">
            <button class="btn btn-warning" onclick="send({type:'rerunAnalysis'})">Re-run Analysis</button>
            <button class="btn btn-secondary" onclick="send({type:'dismissIndexChange'})">Dismiss</button>
        </div>
    </div>
    <div class="finding-header">
        <div class="meta">
            Finding <strong>${current}/${total}</strong> •
            <span class="severity">${escapeHtml(finding.severity)}</span> •
            ${escapeHtml(finding.lens)} •
            ${escapeHtml(lineRange)}
            ${statusHtml}
        </div>
        <div class="evidence">${escapeHtml(finding.evidence)}</div>
        ${finding.impact ? `<div class="impact">${escapeHtml(finding.impact)}</div>` : ''}
        ${optionsHtml}
    </div>

    ${ambiguityButtons}

    <div class="chat" id="chat">${transitionHtml}${initialTurnsHtml}</div>

    <div class="input-area">
        <textarea id="input" placeholder="Discuss this finding..." rows="2"
            onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
        <button class="btn" onclick="sendMessage()">Send</button>
    </div>

    <div class="action-buttons">
        <button class="btn btn-success" onclick="send({type:'accept'})">✓ Accept</button>
        <button class="btn btn-danger" onclick="rejectWithReason()">✗ Reject</button>
        <button class="btn btn-secondary" onclick="send({type:'reviewFinding'})">Review</button>
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

            case 'indexChange': {
                const report = msg.report || {};
                const files = Array.isArray(report.changed_files) ? report.changed_files : [];
                const fileText = files.length > 0 ? files.join(', ') : 'index files';
                const notice = document.getElementById('indexChangeNotice');
                const textEl = document.getElementById('indexChangeText');
                if (notice && textEl) {
                    textEl.textContent = 'Index context changed (' + fileText + '). Findings may be stale. Re-run analysis recommended.';
                    notice.classList.add('visible');
                }
                break;
            }

            case 'indexChangeClear': {
                const notice = document.getElementById('indexChangeNotice');
                if (notice) {
                    notice.classList.remove('visible');
                }
                break;
            }
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
