/**
 * Learning Management — JavaScript for learning.html
 */

const Learning = {
    projectPath: null,
    learningData: null,

    async load() {
        const input = document.getElementById('project-path-input');
        this.projectPath = input.value.trim();

        if (!this.projectPath) {
            this.showToast('Please enter a project path', 'error');
            return;
        }

        try {
            const response = await fetch(`/api/learning?project_path=${encodeURIComponent(this.projectPath)}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to load learning data');
            }

            this.learningData = data;
            this.render(data);
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    render(data) {
        const container = document.getElementById('learning-container');
        container.classList.remove('hidden');

        // Update header
        document.getElementById('project-name').textContent = data.project_name;
        document.getElementById('review-count').textContent = data.review_count;

        // Render each category
        this.renderCategory('preferences', data.preferences);
        this.renderCategory('blind-spots', data.blind_spots);
        this.renderCategory('resolutions', data.resolutions);
        this.renderCategory('ambiguity-intentional', data.ambiguity_intentional);
        this.renderCategory('ambiguity-accidental', data.ambiguity_accidental);

        // Show/hide empty message
        const total = data.preferences.length + data.blind_spots.length + 
                     data.resolutions.length + data.ambiguity_intentional.length + 
                     data.ambiguity_accidental.length;
        
        document.getElementById('no-learning-card').classList.toggle('hidden', total > 0);
    },

    renderCategory(categoryId, entries) {
        const card = document.getElementById(`${categoryId}-card`);
        const list = document.getElementById(`${categoryId}-list`);
        const count = document.getElementById(`${categoryId}-count`);

        if (entries.length === 0) {
            card.classList.add('hidden');
            return;
        }

        card.classList.remove('hidden');
        count.textContent = entries.length;

        list.innerHTML = '';
        entries.forEach(entry => {
            const li = document.createElement('li');
            li.innerHTML = `
                <span class="entry-text">${entry.description}</span>
                <button class="btn btn-small btn-reject" onclick="Learning.deleteEntry(${entry.id}, '${categoryId}')">
                    Delete
                </button>
            `;
            list.appendChild(li);
        });
    },

    async deleteEntry(entryId, categoryId) {
        if (!confirm('Delete this learning entry?')) {
            return;
        }

        try {
            const response = await fetch(`/api/learning/entries/${entryId}?project_path=${encodeURIComponent(this.projectPath)}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to delete entry');
            }

            this.showToast('Entry deleted', 'success');
            this.load(); // Refresh
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    async exportLearning() {
        if (!this.projectPath) {
            this.showToast('Please load learning data first', 'error');
            return;
        }

        try {
            const response = await fetch('/api/learning/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_path: this.projectPath })
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to export learning');
            }

            this.showToast(`LEARNING.md exported to ${data.path}`, 'success');
        } catch (err) {
            this.showToast(err.message, 'error');
        }
    },

    async resetAll() {
        if (!confirm('Reset ALL learning data? This will delete all preferences, blind spots, and resolutions. This cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch(`/api/learning?project_path=${encodeURIComponent(this.projectPath)}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to reset learning');
            }

            this.showToast('Learning data reset', 'success');
            this.load(); // Refresh
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
    }
};
