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

function isSessionStale(session: SessionSummary): boolean {
    return session.status === 'active' && Boolean(session.index_context_stale || session.rerun_recommended);
}

export class SessionsTreeProvider implements vscode.TreeDataProvider<SessionTreeElement> {
    private _onDidChangeTreeData = new vscode.EventEmitter<SessionTreeElement | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private sessions: SessionSummary[] = [];
    private projectPath: string | null = null;
    private apiClient: ApiClient | null = null;
    private currentSessionId: number | null = null;
    private cacheDirty = true;
    private sceneGroupItems: SceneGroupItem[] = [];
    private sessionItemsByGroup: Map<string, SessionTreeItem[]> = new Map();
    private sessionItemsById: Map<number, SessionTreeItem> = new Map();

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
            this.cacheDirty = true;
            this._onDidChangeTreeData.fire();
            return;
        }

        try {
            const result = await this.apiClient.listSessions(this.projectPath);
            this.sessions = result.sessions;
            if (this.currentSessionId !== null && !this.sessions.some((s) => s.id === this.currentSessionId)) {
                this.currentSessionId = null;
            }
            this.cacheDirty = true;
            this._onDidChangeTreeData.fire();
        } catch (err) {
            console.error('Failed to load sessions:', err);
            this.sessions = [];
            this.currentSessionId = null;
            this.cacheDirty = true;
            this._onDidChangeTreeData.fire();
        }
    }

    clear(): void {
        this.sessions = [];
        this.currentSessionId = null;
        this.cacheDirty = true;
        this._onDidChangeTreeData.fire();
    }

    setCurrentSession(sessionId: number | null): void {
        this.currentSessionId = sessionId;
        this.cacheDirty = true;
        this._onDidChangeTreeData.fire();
    }

    getCurrentSessionItem(): SessionTreeItem | undefined {
        this.ensureCache();
        if (this.currentSessionId === null) {
            return undefined;
        }
        return this.sessionItemsById.get(this.currentSessionId);
    }

    setCurrentSessionByScenePath(scenePath: string | undefined): void {
        if (!scenePath) {
            this.setCurrentSession(null);
            return;
        }

        const target = scenePath.toLowerCase();
        const activeMatch = this.sessions.find((s) => {
            if (s.status !== 'active') {
                return false;
            }
            // Check scene_paths first (multi-scene), fall back to scene_path
            const paths = s.scene_paths ?? [s.scene_path];
            return paths.some((p) => p.toLowerCase() === target);
        });
        this.setCurrentSession(activeMatch?.id ?? null);
    }

    getTreeItem(element: SessionTreeElement): vscode.TreeItem {
        return element;
    }

    getChildren(element?: SessionTreeElement): vscode.ProviderResult<SessionTreeElement[]> {
        if (!this.projectPath) {
            return [];
        }

        this.ensureCache();

        if (!element) {
            if (this.sceneGroupItems.length === 0) {
                return [new EmptyStateItem('No sessions found')];
            }

            return this.sceneGroupItems;
        }

        if (element instanceof SceneGroupItem) {
            return this.sessionItemsByGroup.get(element.label) || [];
        }

        return [];
    }

    private ensureCache(): void {
        if (!this.cacheDirty) {
            return;
        }

        this.rebuildCache();
    }

    private rebuildCache(): void {
        const sceneGroupItems = this.buildSceneGroups();
        const sessionItemsByGroup = new Map<string, SessionTreeItem[]>();
        const sessionItemsById = new Map<number, SessionTreeItem>();

        for (const group of sceneGroupItems) {
            const children = this.sortSessions(group.sessions).map((session) => {
                const item = new SessionTreeItem(
                    this.formatSessionLabel(session),
                    this.formatSessionDescription(session),
                    vscode.TreeItemCollapsibleState.None,
                    session,
                    session.id === this.currentSessionId,
                );
                sessionItemsById.set(session.id, item);
                return item;
            });

            sessionItemsByGroup.set(group.label, children);
        }

        this.sceneGroupItems = sceneGroupItems;
        this.sessionItemsByGroup = sessionItemsByGroup;
        this.sessionItemsById = sessionItemsById;
        this.cacheDirty = false;
    }

    private buildSceneGroups(): SceneGroupItem[] {
        const grouped = new Map<string, { sessions: SessionSummary[]; representative: SessionSummary }>();

        for (const session of this.sessions) {
            const sceneLabel = formatSceneSetLabel(session);
            if (!grouped.has(sceneLabel)) {
                grouped.set(sceneLabel, {
                    sessions: [],
                    representative: session,
                });
            }
            grouped.get(sceneLabel)!.sessions.push(session);
        }

        return Array.from(grouped.entries())
            .sort(([sceneA], [sceneB]) => sceneA.localeCompare(sceneB))
            .map(([sceneLabel, group]) => new SceneGroupItem(
                sceneLabel,
                group.sessions,
                formatSceneSetTooltip(group.representative),
            ));
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
        return `#${session.id}`;
    }

    private formatSessionDescription(session: SessionSummary): string {
        const pendingCount = Math.max(
            0,
            session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count,
        );
        const statusLabel = isSessionStale(session) ? `${session.status} · stale` : session.status;
        return `${statusLabel} · total ${session.total_findings} · accepted ${session.accepted_count} · rejected ${session.rejected_count} · withdrawn ${session.withdrawn_count} · pending ${pendingCount}`;
    }
}

/**
 * Format a concise label for a session's scene set.
 * Single-scene: ``01.02.01_scene.txt``
 * Multi-scene:  ``01.02.01_scene.txt +2``
 */
function formatSceneSetLabel(session: SessionSummary): string {
    const paths = session.scene_paths ?? [session.scene_path];
    const primary = path.basename(paths[0] || session.scene_path);
    if (paths.length <= 1) {
        return primary;
    }
    return `${primary} +${paths.length - 1}`;
}

/**
 * Build a tooltip-friendly list of all scene files in a session.
 */
function formatSceneSetTooltip(session: SessionSummary): string {
    const paths = session.scene_paths ?? [session.scene_path];
    if (paths.length <= 1) {
        return `Scene: ${path.basename(paths[0] || session.scene_path)}`;
    }
    return `Scenes (${paths.length}):\n${paths.map((p) => `  ${path.basename(p)}`).join('\n')}`;
}

class SceneGroupItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly sessions: SessionSummary[],
        public readonly tooltipText?: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.Expanded);
        this.contextValue = 'sceneGroup';
        this.resourceUri = vscode.Uri.parse(
            `lit-critic-count://session-group/${encodeURIComponent(label)}?count=${sessions.length}`,
        );
        this.iconPath = new vscode.ThemeIcon('file-submodule');
        this.tooltip = tooltipText ?? label;
        this.id = `scene-group:${label}`;
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
                this.description = description;
            }

            // Set icon by state with stronger visual cues.
            if (isSessionStale(session)) {
                this.iconPath = new vscode.ThemeIcon('warning');
            } else if (session.status === 'active') {
                this.iconPath = new vscode.ThemeIcon('play-circle');
            } else if (session.accepted_count > 0 || session.rejected_count > 0) {
                this.iconPath = new vscode.ThemeIcon('file-binary');
            } else {
                this.iconPath = new vscode.ThemeIcon('file');
            }
            this.id = `session:${session.id}`;
        } else {
            this.contextValue = 'empty';
            this.iconPath = new vscode.ThemeIcon('info');
        }
    }

    private buildTooltip(session: SessionSummary): string {
        const stale = isSessionStale(session);
        const changedIndexes = stale && session.index_changed_files?.length
            ? session.index_changed_files
            : [];
        const lines = [
            `Session #${session.id}`,
            formatSceneSetTooltip(session),
            `Status: ${stale ? `${session.status} (stale)` : session.status}`,
            `Model: ${session.model}`,
            ``,
            `Findings: ${session.total_findings}`,
            `  Accepted: ${session.accepted_count}`,
            `  Rejected: ${session.rejected_count}`,
            `  Withdrawn: ${session.withdrawn_count}`,
            `  Pending: ${Math.max(0, session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count)}`,
            ``,
            ...(changedIndexes.length > 0 ? [`Changed indexes: ${changedIndexes.join(', ')}`, ``] : []),
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
