/**
 * Sessions Tree Provider — sidebar view for managing review sessions.
 *
 * Shows scene-first hierarchy:
 * - Scene file
 *   - Session
 *     - Aggregated findings counters in session details
 *
 * Actions:
 * - Click to view session details
 * - Delete session (context menu)
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { ApiClient } from './apiClient';
import { SessionSummary } from './types';

type SessionTreeElement = SceneGroupItem | SessionTreeItem | EmptyStateItem;

export class SessionsTreeProvider implements vscode.TreeDataProvider<SessionTreeElement> {
    private _onDidChangeTreeData = new vscode.EventEmitter<SessionTreeElement | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private sessions: SessionSummary[] = [];
    private projectPath: string | null = null;
    private apiClient: ApiClient | null = null;
    private currentSessionId: number | null = null;

    constructor() {}

    setApiClient(client: ApiClient): void {
        this.apiClient = client;
    }

    setProjectPath(projectPath: string): void {
        this.projectPath = projectPath;
    }

    async refresh(): Promise<void> {
        if (!this.apiClient || !this.projectPath) {
            this.sessions = [];
            this.currentSessionId = null;
            this._onDidChangeTreeData.fire();
            return;
        }

        try {
            const result = await this.apiClient.listSessions(this.projectPath);
            this.sessions = result.sessions;
            if (this.currentSessionId !== null && !this.sessions.some((s) => s.id === this.currentSessionId)) {
                this.currentSessionId = null;
            }
            this._onDidChangeTreeData.fire();
        } catch (err) {
            console.error('Failed to load sessions:', err);
            this.sessions = [];
            this.currentSessionId = null;
            this._onDidChangeTreeData.fire();
        }
    }

    clear(): void {
        this.sessions = [];
        this.currentSessionId = null;
        this._onDidChangeTreeData.fire();
    }

    setCurrentSession(sessionId: number | null): void {
        this.currentSessionId = sessionId;
        this._onDidChangeTreeData.fire();
    }

    setCurrentSessionByScenePath(scenePath: string | undefined): void {
        if (!scenePath) {
            this.setCurrentSession(null);
            return;
        }

        const target = scenePath.toLowerCase();
        const activeMatch = this.sessions.find(
            (s) => s.status === 'active' && s.scene_path.toLowerCase() === target,
        );
        this.setCurrentSession(activeMatch?.id ?? null);
    }

    getTreeItem(element: SessionTreeElement): vscode.TreeItem {
        return element;
    }

    getChildren(element?: SessionTreeElement): vscode.ProviderResult<SessionTreeElement[]> {
        if (!this.projectPath) {
            return [];
        }

        if (!element) {
            // Root level — group by scene file name
            const sceneGroups = this.buildSceneGroups();
            if (sceneGroups.length === 0) {
                return [new EmptyStateItem('No sessions found')];
            }

            return sceneGroups;
        }

        if (element instanceof SceneGroupItem) {
            return this.sortSessions(element.sessions).map((session) => new SessionTreeItem(
                this.formatSessionLabel(session),
                this.formatSessionDescription(session),
                vscode.TreeItemCollapsibleState.None,
                session,
                session.id === this.currentSessionId,
            ));
        }

        return [];
    }

    private buildSceneGroups(): SceneGroupItem[] {
        const grouped = new Map<string, SessionSummary[]>();

        for (const session of this.sessions) {
            const sceneName = path.basename(session.scene_path);
            if (!grouped.has(sceneName)) {
                grouped.set(sceneName, []);
            }
            grouped.get(sceneName)!.push(session);
        }

        return Array.from(grouped.entries())
            .sort(([sceneA], [sceneB]) => sceneA.localeCompare(sceneB))
            .map(([sceneName, sessions]) => new SceneGroupItem(sceneName, sessions));
    }

    private sortSessions(sessions: SessionSummary[]): SessionSummary[] {
        const statusWeight: Record<SessionSummary['status'], number> = {
            active: 0,
            completed: 1,
            abandoned: 2,
        };

        return [...sessions].sort((a, b) => {
            const statusDelta = statusWeight[a.status] - statusWeight[b.status];
            if (statusDelta !== 0) {
                return statusDelta;
            }

            return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        });
    }

    private formatSessionLabel(session: SessionSummary): string {
        return `Session #${session.id}`;
    }

    private formatSessionDescription(session: SessionSummary): string {
        const pendingCount = Math.max(
            0,
            session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count,
        );
        return `${session.status} · total ${session.total_findings} · accepted ${session.accepted_count} · rejected ${session.rejected_count} · withdrawn ${session.withdrawn_count} · pending ${pendingCount}`;
    }
}

class SceneGroupItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly sessions: SessionSummary[]
    ) {
        super(label, vscode.TreeItemCollapsibleState.Expanded);
        this.contextValue = 'sceneGroup';
        this.description = `${sessions.length}`;
        this.iconPath = new vscode.ThemeIcon('file-submodule');
    }
}

class SessionTreeItem extends vscode.TreeItem {
    constructor(
        public label: string,
        public description: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly session?: SessionSummary,
        public readonly isCurrent: boolean = false,
    ) {
        super(label, collapsibleState);

        if (session) {
            this.contextValue = 'session';
            this.tooltip = this.buildTooltip(session);
            this.command = {
                command: 'literaryCritic.viewSession',
                title: 'View Session Details',
                arguments: [session.id]
            };

            if (isCurrent) {
                this.label = `▶ ${label}`;
                this.description = `current · ${description}`;
            }

            // Set icon by state with stronger visual cues.
            if (isCurrent) {
                this.iconPath = new vscode.ThemeIcon('target');
            } else if (session.status === 'active') {
                this.iconPath = new vscode.ThemeIcon('play-circle');
            } else if (session.accepted_count > 0 || session.rejected_count > 0) {
                this.iconPath = new vscode.ThemeIcon('file-binary');
            } else {
                this.iconPath = new vscode.ThemeIcon('file');
            }
        } else {
            this.contextValue = 'empty';
            this.iconPath = new vscode.ThemeIcon('info');
        }
    }

    private buildTooltip(session: SessionSummary): string {
        const lines = [
            `Session #${session.id}`,
            `Scene: ${path.basename(session.scene_path)}`,
            `Status: ${session.status}`,
            `Model: ${session.model}`,
            ``,
            `Findings: ${session.total_findings}`,
            `  Accepted: ${session.accepted_count}`,
            `  Rejected: ${session.rejected_count}`,
            `  Withdrawn: ${session.withdrawn_count}`,
            `  Pending: ${Math.max(0, session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count)}`,
            ``,
            `Created: ${new Date(session.created_at).toLocaleString()}`,
        ];

        if (session.completed_at) {
            lines.push(`Completed: ${new Date(session.completed_at).toLocaleString()}`);
        }

        return lines.join('\n');
    }
}

class EmptyStateItem extends vscode.TreeItem {
    constructor(label: string) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.contextValue = 'empty';
        this.iconPath = new vscode.ThemeIcon('info');
    }
}
