/**
 * lit-critic Web UI — Frontend Logic
 * 
 * Single-page app with three states: Setup → Analysis → Review
 * Communicates with the FastAPI backend via REST endpoints.
 */

const App = {
    // --- State ---
    sessionSummary: null,
    currentFinding: null,

    // --- Init ---
    init() {
        // Restore saved form values from localStorage
        const savedProject = localStorage.getItem('lc_project_path');
        const savedScene = localStorage.getItem('lc_scene_path');
        if (savedProject) document.getElementById('project-path').value = savedProject;
        if (savedScene) document.getElementById('scene-path').value = savedScene;

        // Check if API key is already configured server-side
        App.checkApiKeyConfig();

        // Setup form handler
        document.getElementById('setup-form').addEventListener('submit', (e) => {
            e.preventDefault();
            App.startAnalysis();
        });

        // Check session button
        document.getElementById('check-session-btn').addEventListener('click', () => {
            App.checkSavedSession();
        });

        // Resume button
        document.getElementById('resume-btn').addEventListener('click', () => {
            App.resumeSession();
        });

        // Glossary toggle
        document.getElementById('glossary-toggle').addEventListener('click', () => {
            const list = document.getElementById('glossary-list');
            const icon = document.querySelector('.toggle-icon');
            list.classList.toggle('collapsed');
            icon.classList.toggle('open');
        });
    },

    // --- View Management ---
    showView(viewId) {
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById(viewId).classList.add('active');
    },

    // --- API Helpers ---
    async api(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);

        const res = await fetch(`/api${path}`, opts);
        const data = await res.json();

        if (!res.ok) {
            const detail = data.detail ?? `HTTP ${res.status}`;
            if (typeof detail === 'string') {
                throw new Error(`HTTP ${res.status}: ${detail}`);
            }
            throw new Error(`HTTP ${res.status}: ${JSON.stringify(detail)}`);
        }
        return data;
    },

    // --- Toast Notifications ---
    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => el.remove(), 4000);
    },

    // --- Config ---
    async checkApiKeyConfig() {
        try {
            const config = await App.api('GET', '/config');
            if (config.api_key_configured) {
                const configured = config.api_keys_configured || {};
                const providers = Object.entries(configured)
                    .filter(([, ok]) => Boolean(ok))
                    .map(([provider]) => provider.toUpperCase());

                const textEl = document.getElementById('api-key-configured-text');
                if (textEl && providers.length > 0) {
                    textEl.textContent = `✓ API key configured for ${providers.join(', ')} (environment / .env)`;
                }

                document.getElementById('api-key-configured').classList.remove('hidden');
            }
            // Populate model selector
            if (config.available_models) {
                App.populateModelSelector(config.available_models, config.default_model);
            }
        } catch (err) {
            // If the check fails, just show the input as usual
        }
    },

    populateModelSelector(models, defaultModel) {
        const select = document.getElementById('model-select');
        select.innerHTML = '';
        const savedModel = localStorage.getItem('lc_model');

        for (const [name, info] of Object.entries(models)) {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = `${name} — ${info.label}`;
            if (savedModel ? name === savedModel : name === defaultModel) {
                option.selected = true;
            }
            select.appendChild(option);
        }

        // Also populate discussion model selector
        const discussionSelect = document.getElementById('discussion-model-select');
        discussionSelect.innerHTML = '<option value="">Same as analysis model</option>';
        const savedDiscussionModel = localStorage.getItem('lc_discussion_model');

        for (const [name, info] of Object.entries(models)) {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = `${name} — ${info.label}`;
            if (savedDiscussionModel && name === savedDiscussionModel) {
                option.selected = true;
            }
            discussionSelect.appendChild(option);
        }
    },

    // --- Setup Actions ---
    async startAnalysis() {
        const projectPath = document.getElementById('project-path').value.trim();
        const scenePath = document.getElementById('scene-path').value.trim();
        const apiKey = document.getElementById('api-key').value.trim();
        const discussionApiKey = document.getElementById('discussion-api-key').value.trim();

        if (!projectPath || !scenePath) {
            App.toast('Please fill in project directory and scene file.', 'error');
            return;
        }

        const model = document.getElementById('model-select').value;
        const discussionModel = document.getElementById('discussion-model-select').value;

        // Save to localStorage
        localStorage.setItem('lc_project_path', projectPath);
        localStorage.setItem('lc_scene_path', scenePath);
        localStorage.setItem('lc_model', model);
        localStorage.setItem('lc_discussion_model', discussionModel);

        // Switch to analysis view
        App.showView('analysis-view');
        App.resetAnalysisProgress();

        // Start SSE listener for progress
        App.listenToProgress();

        try {
            const result = await App.api('POST', '/analyze', {
                scene_path: scenePath,
                project_path: projectPath,
                api_key: apiKey || null,
                discussion_api_key: discussionApiKey || null,
                model: model,
                discussion_model: discussionModel || null,
            });

            App.sessionSummary = result;
            App.enterReview(result);
        } catch (err) {
            document.getElementById('analysis-error').textContent = err.message;
            document.getElementById('analysis-error').classList.remove('hidden');
        }
    },

    resetAnalysisProgress() {
        document.querySelectorAll('.lens-item').forEach(el => {
            el.className = 'lens-item';
            el.querySelector('.lens-icon').textContent = '⏳';
        });
        document.getElementById('coordination-status').classList.add('hidden');
        document.getElementById('analysis-error').classList.add('hidden');
    },

    listenToProgress() {
        const evtSource = new EventSource('/api/analyze/progress');

        evtSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'lens_complete') {
                const item = document.querySelector(`.lens-item[data-lens="${data.lens}"]`);
                if (item) {
                    item.classList.add('complete');
                    item.querySelector('.lens-icon').textContent = '✓';
                }
            } else if (data.type === 'lens_error') {
                const item = document.querySelector(`.lens-item[data-lens="${data.lens}"]`);
                if (item) {
                    item.classList.add('error');
                    item.querySelector('.lens-icon').textContent = '✗';
                }
            } else if (data.type === 'status' && data.message && data.message.includes('Coordinating')) {
                document.getElementById('coordination-status').classList.remove('hidden');
            } else if (data.type === 'complete') {
                const coordEl = document.getElementById('coordination-status');
                coordEl.innerHTML = '<span class="lens-icon">✓</span> Coordination complete';
                coordEl.classList.remove('hidden');
            } else if (data.type === 'error') {
                document.getElementById('analysis-error').textContent = data.message;
                document.getElementById('analysis-error').classList.remove('hidden');
            } else if (data.type === 'done') {
                evtSource.close();
            }
        };

        evtSource.onerror = () => {
            evtSource.close();
        };
    },

    async checkSavedSession() {
        const projectPath = document.getElementById('project-path').value.trim();
        if (!projectPath) {
            App.toast('Enter a project directory first.', 'error');
            return;
        }

        try {
            const result = await App.api('POST', '/check-session', { project_path: projectPath });

            if (result.exists) {
                const info = document.getElementById('saved-session-info');
                const details = document.getElementById('saved-session-details');
                const sceneName = result.scene_path.split(/[/\\]/).pop();
                details.textContent = `Scene: ${sceneName} — Saved: ${result.saved_at} — Progress: ${result.current_index}/${result.total_findings} findings`;
                info.classList.remove('hidden');
            } else {
                App.toast('No saved session found for this project.', 'info');
            }
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    async resumeSession() {
        const projectPath = document.getElementById('project-path').value.trim();
        const apiKey = document.getElementById('api-key').value.trim();
        const discussionApiKey = document.getElementById('discussion-api-key').value.trim();

        if (!projectPath) {
            App.toast('Enter a project directory first.', 'error');
            return;
        }

        try {
            const result = await App.api('POST', '/resume', {
                project_path: projectPath,
                api_key: apiKey || null,
                discussion_api_key: discussionApiKey || null,
            });

            App.sessionSummary = result;
            App.enterReview(result);
            App.toast(`Resumed session — starting at finding #${result.current_index + 1}`, 'success');
        } catch (err) {
            if (err.message.includes('scene_path_not_found')) {
                const detail = App.tryParseResumeErrorDetail(err.message);
                if (detail) {
                    const suggested = detail.saved_scene_path || detail.attempted_scene_path || '';
                    const correctedPath = window.prompt(
                        `Saved scene path could not be found.\n` +
                        `Old path:\n${suggested}\n\n` +
                        `Enter corrected scene file path:`,
                        suggested
                    );

                    if (!correctedPath || !correctedPath.trim()) {
                        App.toast('Resume cancelled.', 'info');
                        return;
                    }

                    try {
                        const retry = await App.api('POST', '/resume', {
                            project_path: projectPath,
                            api_key: apiKey || null,
                            discussion_api_key: discussionApiKey || null,
                            scene_path_override: correctedPath.trim(),
                        });

                        App.sessionSummary = retry;
                        App.enterReview(retry);
                        App.toast(`Resumed session — starting at finding #${retry.current_index + 1}`, 'success');
                        return;
                    } catch (retryErr) {
                        App.toast(retryErr.message, 'error');
                        return;
                    }
                }
            }

            App.toast(err.message, 'error');
        }
    },

    tryParseResumeErrorDetail(message) {
        const match = message.match(/^HTTP\s+\d+:\s+(\{.*\})$/);
        if (!match) return null;
        try {
            const detail = JSON.parse(match[1]);
            if (detail && detail.code === 'scene_path_not_found') {
                return detail;
            }
        } catch {
            // ignore parse errors
        }
        return null;
    },

    // --- Review Mode ---
    enterReview(summary) {
        App.showView('review-view');

        // Update summary bar
        document.getElementById('count-critical').textContent = summary.counts.critical;
        document.getElementById('count-major').textContent = summary.counts.major;
        document.getElementById('count-minor').textContent = summary.counts.minor;

        // Show model label(s)
        if (summary.model) {
            let modelText = `Analysis: ${summary.model.label}`;
            if (summary.discussion_model) {
                modelText += ` · Discussion: ${summary.discussion_model.label}`;
            }
            document.getElementById('model-label').textContent = modelText;
        }

        // Glossary issues
        const glossaryIssues = summary.glossary_issues || [];
        if (glossaryIssues.length > 0) {
            document.getElementById('glossary-section').classList.remove('hidden');
            const list = document.getElementById('glossary-list');
            list.innerHTML = '';
            glossaryIssues.forEach(issue => {
                const li = document.createElement('li');
                li.textContent = issue;
                list.appendChild(li);
            });
        }

        // Load first finding
        App.loadCurrentFinding();
    },

    async loadCurrentFinding() {
        try {
            const data = await App.api('GET', '/finding');
            App.handleFindingResponse(data);
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    handleFindingResponse(data) {
        if (data.complete) {
            // Show complete card, hide finding + discussion + actions
            document.getElementById('finding-card').classList.add('hidden');
            document.getElementById('discussion-section').classList.add('hidden');
            document.querySelector('.actions-bar').classList.add('hidden');
            document.getElementById('complete-card').classList.remove('hidden');
            return;
        }

        // Show finding, hide complete
        document.getElementById('finding-card').classList.remove('hidden');
        document.getElementById('discussion-section').classList.remove('hidden');
        document.querySelector('.actions-bar').classList.remove('hidden');
        document.getElementById('complete-card').classList.add('hidden');

        App.currentFinding = data;
        App.renderFinding(data);
    },

    renderFinding(data) {
        const f = data.finding;
        const severity = (f.severity || '').toLowerCase();
        const lens = (f.lens || '').toLowerCase();

        // Update progress
        document.getElementById('progress-text').textContent = `${data.current} / ${data.total}`;

        // Finding number
        document.getElementById('finding-number').textContent = `#${f.number}`;

        // Severity badge
        const sevBadge = document.getElementById('finding-severity');
        sevBadge.textContent = (f.severity || '').toUpperCase();
        sevBadge.className = `severity-badge ${severity}`;

        // Lens badge
        const lensBadge = document.getElementById('finding-lens');
        lensBadge.textContent = (f.lens || '').toUpperCase();
        lensBadge.className = `lens-badge ${lens}`;

        // Finding card severity styling
        const card = document.getElementById('finding-card');
        card.className = `card finding-card severity-${severity}`;

        // Flagged by
        const flagged = document.getElementById('finding-flagged');
        if (f.flagged_by && f.flagged_by.length > 1) {
            flagged.textContent = `Flagged by: ${f.flagged_by.join(', ')}`;
        } else {
            flagged.textContent = '';
        }

        // Body fields
        document.getElementById('finding-location').textContent = f.location || 'Not specified';
        document.getElementById('finding-evidence').textContent = f.evidence || 'Not specified';
        document.getElementById('finding-impact').textContent = f.impact || 'Not specified';

        // Options
        const optionsList = document.getElementById('finding-options');
        optionsList.innerHTML = '';
        (f.options || []).forEach(opt => {
            const li = document.createElement('li');
            li.textContent = opt;
            optionsList.appendChild(li);
        });

        // Ambiguity notice
        const ambiguity = document.getElementById('ambiguity-notice');
        if (data.is_ambiguity) {
            ambiguity.classList.remove('hidden');
        } else {
            ambiguity.classList.add('hidden');
        }

        // Render persisted discussion thread for this finding unless we are
        // intentionally preserving the already-rendered live thread.
        if (!data._preserveDiscussion) {
            App.renderDiscussionTurns(f.discussion_turns || []);
            document.getElementById('discussion-input').value = '';
        }
    },

    renderDiscussionTurns(turns) {
        const thread = document.getElementById('discussion-thread');
        thread.innerHTML = '';

        (turns || []).forEach(turn => {
            const role = (turn.role || '').toLowerCase();
            if (role === 'user') {
                App.addDiscussionMessage('You', turn.content || '', 'user');
            } else if (role === 'assistant') {
                App.addDiscussionMessage('Critic', turn.content || '', 'critic');
            } else {
                App.addDiscussionMessage('System', turn.content || '', 'system');
            }
        });
    },

    // --- Scene Change Handling ---
    handleSceneChange(report) {
        // Show a system message in the discussion thread
        const parts = ['📝 Scene change detected'];
        if (report.adjusted) parts.push(`${report.adjusted} finding(s) adjusted`);
        if (report.stale) parts.push(`${report.stale} finding(s) marked stale`);
        if (report.re_evaluated && report.re_evaluated.length > 0) {
            for (const r of report.re_evaluated) {
                parts.push(`Finding #${r.finding_number} → ${r.status}`);
            }
        }
        App.addDiscussionMessage('System', parts.join(' · '), 'system');
        App.toast('Scene change detected — critic will see your edits', 'info');
    },

    // --- Finding Actions ---
    async continueFinding() {
        try {
            const data = await App.api('POST', '/finding/continue');
            App.handleFindingResponse(data);
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    async acceptFinding() {
        try {
            const data = await App.api('POST', '/finding/accept');
            App.toast(`Finding #${data.action.finding_number} accepted`, 'success');
            App.handleFindingResponse(data.next);
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    rejectFinding() {
        // Show modal for reason
        document.getElementById('reject-modal').classList.remove('hidden');
        document.getElementById('reject-reason').value = '';
        document.getElementById('reject-reason').focus();
    },

    async confirmReject() {
        const reason = document.getElementById('reject-reason').value.trim();
        document.getElementById('reject-modal').classList.add('hidden');

        try {
            const data = await App.api('POST', '/finding/reject', { reason });
            App.toast(`Finding #${data.action.finding_number} rejected`, 'info');
            App.handleFindingResponse(data.next);
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    cancelReject() {
        document.getElementById('reject-modal').classList.add('hidden');
    },

    async reviewFinding() {
        try {
            const data = await App.api('POST', '/finding/review');
            if (data.review?.changed) {
                App.handleSceneChange(data.review);
            } else if (data.review?.message) {
                App.toast(data.review.message, 'info');
            } else {
                App.toast('Current finding reviewed against scene edits', 'info');
            }
            App.handleFindingResponse(data);
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    async skipTo(lens) {
        try {
            const data = await App.api('POST', `/finding/skip-to/${lens}`);
            App.toast(`Skipped to ${lens} findings`, 'info');
            App.handleFindingResponse(data);
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    async markAmbiguity(intentional) {
        try {
            const data = await App.api('POST', '/finding/ambiguity', { intentional });
            const label = intentional ? 'intentional' : 'accidental';
            App.toast(`Marked as ${label} ambiguity`, 'info');
            document.getElementById('ambiguity-notice').classList.add('hidden');
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    // --- Discussion (streamed token-by-token) ---
    async discuss() {
        const input = document.getElementById('discussion-input');
        const message = input.value.trim();
        if (!message) return;

        // Add user message to thread
        App.addDiscussionMessage('You', message, 'user');
        input.value = '';

        // Show loading indicator
        document.getElementById('discussion-loading').classList.remove('hidden');

        // Create the critic message element for streaming into
        const thread = document.getElementById('discussion-thread');
        const msgEl = document.createElement('div');
        msgEl.className = 'discussion-msg critic';
        msgEl.innerHTML = '<div class="msg-label">Critic</div><div class="msg-content"></div>';
        thread.appendChild(msgEl);
        const contentEl = msgEl.querySelector('.msg-content');

        try {
            const response = await fetch('/api/finding/discuss/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || `HTTP ${response.status}`);
            }

            // Hide loading — streaming has started
            document.getElementById('discussion-loading').classList.add('hidden');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let doneData = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE events from buffer
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line in buffer

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const jsonStr = line.slice(6);
                    try {
                        const event = JSON.parse(jsonStr);
                        if (event.type === 'scene_change') {
                            App.handleSceneChange(event);
                        } else if (event.type === 'token') {
                            contentEl.textContent += event.text;
                            thread.scrollTop = thread.scrollHeight;
                        } else if (event.type === 'done') {
                            doneData = event;
                        }
                    } catch (e) {
                        // Ignore malformed JSON
                    }
                }
            }

            // Process final result
            if (doneData) {
                // Update the message content with the cleaned response
                contentEl.textContent = doneData.response || contentEl.textContent;

                if (doneData.status === 'accepted') {
                    App.toast('Finding accepted by discussion', 'success');
                } else if (doneData.status === 'rejected' || doneData.status === 'conceded') {
                    App.toast('Finding dismissed by discussion', 'info');
                } else if (doneData.status === 'revised') {
                    App.toast('Finding revised by critic', 'info');
                } else if (doneData.status === 'withdrawn') {
                    App.toast('Finding withdrawn by critic', 'info');
                } else if (doneData.status === 'escalated') {
                    App.toast('Finding escalated by critic', 'warning');
                }

                // Re-render the finding card if the finding was updated
                // (by discussion revision, scene change re-evaluation, or line adjustment)
                if (doneData.finding && App.currentFinding) {
                    App.currentFinding.finding = doneData.finding;
                    App.currentFinding._preserveDiscussion = true;
                    App.renderFinding(App.currentFinding);
                    delete App.currentFinding._preserveDiscussion;

                    // Sync thread with canonical persisted turns from backend.
                    if (doneData.finding.discussion_turns) {
                        App.renderDiscussionTurns(doneData.finding.discussion_turns);
                    }
                }
            }
        } catch (err) {
            document.getElementById('discussion-loading').classList.add('hidden');
            // If streaming failed, remove the empty critic bubble and fall back
            if (!contentEl.textContent) {
                msgEl.remove();
            }
            App.toast(err.message, 'error');
        }
    },

    addDiscussionMessage(label, text, role) {
        const thread = document.getElementById('discussion-thread');
        const msg = document.createElement('div');
        msg.className = `discussion-msg ${role}`;
        msg.innerHTML = `<div class="msg-label">${label}</div><div>${App.escapeHtml(text)}</div>`;
        thread.appendChild(msg);
        thread.scrollTop = thread.scrollHeight;
    },

    // --- Session Actions ---
    async saveLearning() {
        try {
            const data = await App.api('POST', '/learning/save');
            App.toast(`LEARNING.md saved to ${data.path}`, 'success');
        } catch (err) {
            App.toast(err.message, 'error');
        }
    },

    backToSetup() {
        App.sessionSummary = null;
        App.currentFinding = null;
        App.showView('setup-view');

        // Reset review view state
        document.getElementById('finding-card').classList.remove('hidden');
        document.getElementById('discussion-section').classList.remove('hidden');
        document.querySelector('.actions-bar').classList.remove('hidden');
        document.getElementById('complete-card').classList.add('hidden');
        document.getElementById('glossary-section').classList.add('hidden');
    },

    // --- Utilities ---
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
