import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { ApiClient } from './apiClient';
import { IndexProjection, SceneProjection } from './types';

type SourceStatus = 'fresh' | 'stale' | 'missing' | 'not_indexed' | 'error';

interface SourceSnapshot {
    label: 'CANON.md' | 'STYLE.md';
    uri: vscode.Uri;
    status: SourceStatus;
    refreshedAt: string | null;
}

type ScenesTreeElement = SourceGroupItem | SourceItem | SceneGroupItem | SceneTreeItem | EmptyStateItem;

function isSceneStale(scene: SceneProjection): boolean {
    return Boolean(scene.stale);
}

function toSceneUri(projectPath: string, scenePath: string): vscode.Uri {
    if (path.isAbsolute(scenePath)) {
        return vscode.Uri.file(scenePath);
    }

    return vscode.Uri.file(path.join(projectPath, ...scenePath.split('/')));
}

export class ScenesTreeProvider implements vscode.TreeDataProvider<ScenesTreeElement> {
    private _onDidChangeTreeData = new vscode.EventEmitter<ScenesTreeElement | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private scenes: SceneProjection[] = [];
    private sources: SourceSnapshot[] = [];
    private projectPath: string | null = null;
    private apiClient: ApiClient | null = null;
    private staleInputPaths: Set<string> = new Set<string>();

    setStaleInputPaths(paths: Set<string>): void {
        this.staleInputPaths = new Set(paths);
        this._onDidChangeTreeData.fire();
    }

    setApiClient(client: ApiClient): void {
        this.apiClient = client;
    }

    setProjectPath(projectPath: string): void {
        this.projectPath = projectPath;
    }

    async refresh(): Promise<void> {
        if (!this.apiClient || !this.projectPath) {
            this.scenes = [];
            this._onDidChangeTreeData.fire();
            return;
        }

        try {
            let indexesError = false;
            const [sceneResult, indexResult] = await Promise.all([
                (this.apiClient as ApiClient & {
                    getScenes: (projectPath: string) => Promise<{ scenes: SceneProjection[] }>;
                }).getScenes(this.projectPath),
                this.apiClient.getIndexes(this.projectPath).catch(() => {
                    indexesError = true;
                    return { indexes: [] as IndexProjection[] };
                }),
            ]);
            this.scenes = sceneResult.scenes;
            this.sources = this.buildSourceSnapshots(this.projectPath, indexResult.indexes, indexesError);
            this._onDidChangeTreeData.fire();
        } catch (err) {
            console.error('Failed to load scenes:', err);
            this.scenes = [];
            this.sources = this.buildSourceSnapshots(this.projectPath, [], true);
            this._onDidChangeTreeData.fire();
        }
    }

    clear(): void {
        this.scenes = [];
        this.sources = [];
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: ScenesTreeElement): vscode.TreeItem {
        return element;
    }

    getChildren(element?: ScenesTreeElement): vscode.ProviderResult<ScenesTreeElement[]> {
        if (element instanceof SourceGroupItem) {
            return this.sources.map((source) => {
                const overrideStale = this.staleInputPaths.has(source.uri.fsPath);
                const status: SourceStatus = overrideStale ? 'stale' : source.status;
                return new SourceItem({ ...source, status });
            });
        }

        if (element instanceof SceneGroupItem) {
            return this.projectPath && this.scenes.length > 0
                ? [...this.scenes]
                    .sort((a, b) => a.scene_path.localeCompare(b.scene_path))
                    .map((scene) => {
                        const sceneUri = toSceneUri(this.projectPath!, scene.scene_path);
                        const staleOverride = this.staleInputPaths.has(sceneUri.fsPath);
                        return new SceneTreeItem(
                            staleOverride ? { ...scene, stale: true } : scene,
                            sceneUri,
                        );
                    })
                : [new EmptyStateItem('No scenes found')];
        }

        if (element) {
            return [];
        }

        return [new SourceGroupItem(), new SceneGroupItem()];
    }

    private buildSourceSnapshots(
        projectPath: string,
        indexes: IndexProjection[],
        indexesError = false,
    ): SourceSnapshot[] {
        const findProjection = (token: 'canon' | 'style'): IndexProjection | undefined =>
            indexes.find((projection) => projection.index_name.toLowerCase().includes(token));

        const resolveStatus = (projection: IndexProjection | undefined, filePath: string): SourceStatus => {
            if (indexesError) {
                return 'error';
            }
            if (projection) {
                return projection.stale ? 'stale' : 'fresh';
            }
            return fs.existsSync(filePath) ? 'not_indexed' : 'missing';
        };

        const canon = findProjection('canon');
        const style = findProjection('style');
        const canonPath = path.join(projectPath, 'CANON.md');
        const stylePath = path.join(projectPath, 'STYLE.md');

        return [
            {
                label: 'CANON.md',
                uri: vscode.Uri.file(canonPath),
                status: resolveStatus(canon, canonPath),
                refreshedAt: canon?.last_refreshed_at ?? null,
            },
            {
                label: 'STYLE.md',
                uri: vscode.Uri.file(stylePath),
                status: resolveStatus(style, stylePath),
                refreshedAt: style?.last_refreshed_at ?? null,
            },
        ];
    }
}

export class SceneTreeItem extends vscode.TreeItem {
    constructor(
        public readonly scene: SceneProjection,
        public readonly sceneUri: vscode.Uri,
    ) {
        super(path.basename(scene.scene_path), vscode.TreeItemCollapsibleState.None);

        this.id = `scene:${scene.scene_path}`;
        this.contextValue = 'sceneProjection';
        this.resourceUri = isSceneStale(scene)
            ? vscode.Uri.parse(`source-stale://scene/${encodeURIComponent(scene.scene_path)}`)
            : sceneUri;
        this.iconPath = new vscode.ThemeIcon(isSceneStale(scene) ? 'warning' : 'file');
        this.description = scene.scene_id
            ? `${scene.scene_id}${isSceneStale(scene) ? ' · stale' : ''}`
            : (isSceneStale(scene) ? 'stale' : undefined);
        this.tooltip = this.buildTooltip(scene);
        this.command = {
            command: 'vscode.open',
            title: 'Open Scene',
            arguments: [sceneUri],
        };
    }

    private buildTooltip(scene: SceneProjection): string {
        const meta = scene.meta_json && typeof scene.meta_json === 'object'
            ? Object.entries(scene.meta_json)
                .map(([key, value]) => `${key}: ${String(value)}`)
                .join('\n')
            : null;

        const lines = [
            `Scene: ${scene.scene_path}`,
            ...(scene.scene_id ? [`ID: ${scene.scene_id}`] : []),
            `Status: ${isSceneStale(scene) ? 'stale' : 'fresh'}`,
            ...(scene.last_refreshed_at ? [`Refreshed: ${new Date(scene.last_refreshed_at).toLocaleString()}`] : []),
            ...(meta ? ['', meta] : []),
        ];

        return lines.join('\n');
    }
}

class SourceGroupItem extends vscode.TreeItem {
    constructor() {
        super('References', vscode.TreeItemCollapsibleState.Expanded);
        this.id = 'inputs:sources';
        this.contextValue = 'inputSourcesGroup';
        this.iconPath = new vscode.ThemeIcon('book');
    }
}

class SceneGroupItem extends vscode.TreeItem {
    constructor() {
        super('Scenes', vscode.TreeItemCollapsibleState.Expanded);
        this.id = 'inputs:scenes';
        this.contextValue = 'inputScenesGroup';
        this.iconPath = new vscode.ThemeIcon('files');
    }
}

const SOURCE_STATUS_META: Record<SourceStatus, { icon: string; hint: string }> = {
    fresh:       { icon: 'book',    hint: 'Up to date.' },
    stale:       { icon: 'warning', hint: 'File has changed since it was last indexed. Run a session to re-index it.' },
    missing:     { icon: 'error',   hint: 'File not found in the project root. Create it to enable related checks.' },
    not_indexed: { icon: 'info',    hint: 'File exists but has not been indexed yet. Run a session to index it.' },
    error:       { icon: 'error',   hint: 'Could not retrieve index status from the server. Check that the core server is running.' },
};

class SourceItem extends vscode.TreeItem {
    constructor(snapshot: SourceSnapshot) {
        super(snapshot.label, vscode.TreeItemCollapsibleState.None);
        this.id = `inputs:source:${snapshot.label}`;
        this.contextValue = 'inputSource';
        const { status } = snapshot;
        const meta = SOURCE_STATUS_META[status];
        this.resourceUri = status === 'stale'
            ? vscode.Uri.parse(`source-stale://${snapshot.label}`)
            : snapshot.uri;
        this.description = status.replace('_', ' ');
        this.iconPath = new vscode.ThemeIcon(meta.icon);
        this.command = {
            command: 'vscode.open',
            title: 'Open Source File',
            arguments: [snapshot.uri],
        };
        const refreshLine = snapshot.refreshedAt
            ? `\nRefreshed: ${new Date(snapshot.refreshedAt).toLocaleString()}`
            : '';
        this.tooltip = `${snapshot.label}\nStatus: ${status.replace('_', ' ')}\n${meta.hint}${refreshLine}`;
    }
}

class EmptyStateItem extends vscode.TreeItem {
    constructor(label: string) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.contextValue = 'empty';
        this.iconPath = new vscode.ThemeIcon('info');
    }
}
