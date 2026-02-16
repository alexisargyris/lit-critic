/**
 * Sessions Management — JavaScript for sessions.html
 */

const Sessions = {
    projectPath: null,

    async load() {
        const input = document.getElementById('project-path-input');
        this.projectPath = input.value.trim();

        if (!this.projectPath) {
            this.showToast('Please enter a project path', 'error');
            return;
        }

        try {
            const response = await fetch(`/api/sessions?project_path=${encodeURIComponent(this.projectPath)}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to load sessions');
            }

            this.render(data.sessions);
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    render(sessions) {
        const container = document.getElementById('sessions-container');
        const activeCard = document.getElementById('active-sessions-card');
        const completedCard = document.getElementById('completed-sessions-card');
        const abandonedCard = document.getElementById('abandoned-sessions-card');
        const noSessionsCard = document.getElementById('no-sessions-card');

        // Group sessions by status
        const active = sessions.filter(s => s.status === 'active');
        const completed = sessions.filter(s => s.status === 'completed');
        const abandoned = sessions.filter(s => s.status === 'abandoned');

        container.classList.remove('hidden');

        // Hide all cards initially
        activeCard.classList.add('hidden');
        completedCard.classList.add('hidden');
        abandonedCard.classList.add('hidden');
        noSessionsCard.classList.add('hidden');

        if (sessions.length === 0) {
            noSessionsCard.classList.remove('hidden');
            return;
        }

        // Render each group
        if (active.length > 0) {
            activeCard.classList.remove('hidden');
            this.renderTable('active-sessions-body', active, true);
        }

        if (completed.length > 0) {
            completedCard.classList.remove('hidden');
            this.renderTable('completed-sessions-body', completed, false);
        }

        if (abandoned.length > 0) {
            abandonedCard.classList.remove('hidden');
            this.renderTable('abandoned-sessions-body', abandoned, false);
        }
    },

    renderTable(bodyId, sessions, isActive) {
        const tbody = document.getElementById(bodyId);
        tbody.innerHTML = '';

        sessions.forEach(session => {
            const row = document.createElement('tr');
            
            const sceneName = session.scene_path.split(/[/\\]/).pop();
            const created = new Date(session.created_at).toLocaleDateString();

            if (isActive) {
                row.innerHTML = `
                    <td>${session.id}</td>
                    <td class="scene-name">${sceneName}</td>
                    <td>${session.total_findings}</td>
                    <td>${session.model}</td>
                    <td>${created}</td>
                    <td class="session-actions">
                        <button class="btn btn-small" onclick="Sessions.viewDetail(${session.id})">View</button>
                        <button class="btn btn-small btn-reject" onclick="Sessions.deleteSession(${session.id})">Delete</button>
                    </td>
                `;
            } else {
                const stats = `${session.accepted_count}/${session.rejected_count}`;
                row.innerHTML = `
                    <td>${session.id}</td>
                    <td class="scene-name">${sceneName}</td>
                    <td>${session.total_findings}</td>
                    <td>${stats}</td>
                    <td>${created}</td>
                    <td class="session-actions">
                        <button class="btn btn-small" onclick="Sessions.viewDetail(${session.id})">View</button>
                        <button class="btn btn-small btn-reject" onclick="Sessions.deleteSession(${session.id})">Delete</button>
                    </td>
                `;
            }

            tbody.appendChild(row);
        });
    },

    async viewDetail(sessionId) {
        try {
            const response = await fetch(`/api/sessions/${sessionId}?project_path=${encodeURIComponent(this.projectPath)}`);
            const session = await response.json();

            if (!response.ok) {
                throw new Error(session.detail || 'Failed to load session detail');
            }

            this.showDetail(session);
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    showDetail(session) {
        const modal = document.getElementById('detail-modal');
        const title = document.getElementById('detail-title');
        const body = document.getElementById('detail-body');

        title.textContent = `Session #${session.id}`;

        const sceneName = session.scene_path.split(/[/\\]/).pop();
        const created = new Date(session.created_at).toLocaleString();
        const completed = session.completed_at ? new Date(session.completed_at).toLocaleString() : 'N/A';

        let html = `
            <p><strong>Status:</strong> ${session.status}</p>
            <p><strong>Scene:</strong> ${sceneName}</p>
            <p><strong>Model:</strong> ${session.model}</p>
            <p><strong>Created:</strong> ${created}</p>
            <p><strong>Completed:</strong> ${completed}</p>
            <p style="margin-top: 1rem;"><strong>Findings:</strong> ${session.total_findings} total</p>
            <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                <li>Accepted: ${session.accepted_count}</li>
                <li>Rejected: ${session.rejected_count}</li>
                <li>Withdrawn: ${session.withdrawn_count}</li>
            </ul>
        `;

        if (session.findings && session.findings.length > 0) {
            html += '<p style="margin-top: 1rem;"><strong>Finding Details:</strong></p>';
            html += '<div style="max-height: 300px; overflow-y: auto; margin-top: 0.5rem;">';
            session.findings.forEach(f => {
                const evidence = f.evidence.slice(0, 100);
                const turns = Array.isArray(f.discussion_turns) ? f.discussion_turns : [];
                const turnsHtml = turns.length > 0
                    ? `<details style="margin-top: 0.4rem;">
                         <summary style="cursor: pointer; color: var(--text-muted);">Discussion thread (${turns.length} turn${turns.length === 1 ? '' : 's'})</summary>
                         <div style="margin-top: 0.4rem; padding-left: 0.5rem; border-left: 2px solid var(--border-color);">
                            ${turns.map(t => {
                                const role = (t.role || '').toLowerCase() === 'user' ? 'You' : ((t.role || '').toLowerCase() === 'assistant' ? 'Critic' : 'System');
                                const content = this.escapeHtml((t.content || '').slice(0, 400));
                                return `<p style="margin-bottom: 0.35rem;"><strong>${role}:</strong> ${content}</p>`;
                            }).join('')}
                         </div>
                       </details>`
                    : '<p style="margin-top: 0.4rem; color: var(--text-muted); font-size: 0.8rem;">No discussion yet.</p>';
                html += `
                    <div style="margin-bottom: 0.75rem; padding: 0.5rem; background: var(--bg-input); border-radius: 4px;">
                        <p style="font-weight: 600;">#${f.number} [${f.severity}] ${f.lens} — ${f.status}</p>
                        <p style="font-size: 0.8rem; color: var(--text-muted);">${evidence}...</p>
                        ${turnsHtml}
                    </div>
                `;
            });
            html += '</div>';
        }

        body.innerHTML = html;
        modal.classList.remove('hidden');
    },

    closeDetail() {
        document.getElementById('detail-modal').classList.add('hidden');
    },

    async deleteSession(sessionId) {
        if (!confirm(`Delete session #${sessionId}? This cannot be undone.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/sessions/${sessionId}?project_path=${encodeURIComponent(this.projectPath)}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to delete session');
            }

            this.showToast(`Session #${sessionId} deleted`, 'success');
            this.load(); // Refresh the list
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// Close modal when clicking outside
document.getElementById('detail-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'detail-modal') {
        Sessions.closeDetail();
    }
});
