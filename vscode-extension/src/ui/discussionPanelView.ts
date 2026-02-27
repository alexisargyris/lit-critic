import { Finding, DiscussionContextTransition } from '../types';

export function getDiscussionPanelHtml(
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
            <button onclick="send({type:'ambiguity', intentional:true})" class="btn btn-primary">Intentional</button>
            <button onclick="send({type:'ambiguity', intentional:false})" class="btn btn-secondary">Accidental</button>
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
.finding-header .status-accepted {
    color: var(--vscode-testing-iconPassed, #4caf50);
    border-color: var(--vscode-testing-iconPassed, #4caf50);
}
.finding-header .status-rejected {
    color: var(--vscode-errorForeground, #f44336);
    border-color: var(--vscode-errorForeground, #f44336);
}
.finding-header .status-withdrawn {
    color: var(--vscode-disabledForeground, #9e9e9e);
    border-color: var(--vscode-disabledForeground, #9e9e9e);
}
.finding-header .status-revised {
    color: var(--vscode-editorInfo-foreground, #2196f3);
    border-color: var(--vscode-editorInfo-foreground, #2196f3);
}
.finding-header .status-escalated {
    color: var(--vscode-editorWarning-foreground, #ff9800);
    border-color: var(--vscode-editorWarning-foreground, #ff9800);
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

/* Chat area — distinct background so it reads as a reserved discussion zone */
.chat {
    flex: 1;
    min-height: 120px;
    overflow-y: auto;
    margin: 8px 0;
    padding: 8px;
    background: var(--vscode-editorWidget-background, var(--vscode-editor-background));
    border: 1px solid var(--vscode-widget-border, var(--vscode-panel-border));
    border-radius: 4px;
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

/* Input area — send arrow lives inside the textarea wrapper */
.input-area {
    position: relative;
    margin-top: 8px;
    flex-shrink: 0;
}
.input-area textarea {
    width: 100%;
    display: block;
    background: var(--input-bg);
    color: var(--input-fg);
    border: 1px solid var(--input-border);
    border-radius: 4px;
    padding: 6px 34px 6px 8px;
    font-family: inherit;
    font-size: inherit;
    resize: vertical;
    min-height: 36px;
    max-height: 40vh;
}
.input-area textarea:focus {
    outline: 1px solid var(--vscode-focusBorder);
}
.send-btn {
    position: absolute;
    right: 6px;
    bottom: 6px;
    background: none;
    border: none;
    padding: 2px 4px;
    cursor: pointer;
    color: var(--input-fg);
    opacity: 0.4;
    font-size: 1.1em;
    line-height: 1;
    border-radius: 3px;
}
.send-btn:hover {
    opacity: 1;
    background: var(--vscode-toolbar-hoverBackground, transparent);
}

/* Buttons — all use VS Code theme tokens, no hard-coded colours */
.btn {
    padding: 4px 12px;
    border: 1px solid transparent;
    border-radius: 4px;
    cursor: pointer;
    font-family: inherit;
    font-size: 0.9em;
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
}
.btn:hover {
    background: var(--vscode-button-secondaryHoverBackground);
}
/* Accept: accent left-border using the theme "passed/success" colour */
.btn-accept {
    border-left: 3px solid var(--vscode-testing-iconPassed, #4caf50);
}
/* Reject: accent left-border using the theme error colour */
.btn-reject {
    border-left: 3px solid var(--vscode-errorForeground, #f44336);
}
/* Primary action (e.g. Re-run Analysis, Intentional) */
.btn-primary {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
}
.btn-primary:hover {
    background: var(--vscode-button-hoverBackground);
}
.btn-secondary {
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
}
.btn-secondary:hover {
    background: var(--vscode-button-secondaryHoverBackground);
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
        <button class="btn btn-primary" onclick="send({type:'rerunAnalysis'})">Re-run Analysis</button>
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
    <textarea id="input" placeholder="Discuss this finding… (Enter to send, Shift+Enter for newline)" rows="2"
        onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
    <button class="send-btn" title="Send (Enter)" onclick="sendMessage()">&#x27A4;</button>
</div>

<div class="action-buttons">
    <button class="btn btn-accept" onclick="send({type:'accept'})">✓ Accept</button>
    <button class="btn btn-reject" onclick="rejectWithReason()">✗ Reject</button>
    <button class="btn" onclick="send({type:'reviewFinding'})">Review</button>
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

/** Escape HTML entities for safe insertion. */
export function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

