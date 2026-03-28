import * as vscode from 'vscode';
import * as path from 'path';
import { ApiClient } from './apiClient';
import { IndexProjection } from './types';

type IndexesTreeElement = IndexTreeItem | EmptyStateItem;

function isIndexStale(indexProjection: IndexProjection): boolean {
    return Boolean(indexProjection.stale);
}

function toIndexUri(projectPath: string, indexName: string): vscode.Uri {
    if (path.isAbsolute(indexName)) {
        return vscode.Uri.file(indexName);
    }

    return vscode.Uri.file(path.join(projectPath, ...indexName.split('/')));
}

export class IndexesTreeProvider implements vscode.TreeDataProvider<IndexesTreeElement> {
    private _onDidChangeTreeData = new vscode.EventEmitter<IndexesTreeElement | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private indexes: IndexProjection[] = [];
    private projectPath: string | null = null;
    private apiClient: ApiClient | null = null;

    setApiClient(client: ApiClient): void {
        this.apiClient = client;
    }

    setProjectPath(projectPath: string): void {
        this.projectPath = projectPath;
    }

    async refresh(): Promise<void> {
        if (!this.apiClient || !this.projectPath) {
            this.indexes = [];
            this._onDidChangeTreeData.fire();
            return;
        }

        try {
            const result = await (this.apiClient as ApiClient & {
                getIndexes: (projectPath: string) => Promise<{ indexes: IndexProjection[] }>;
            }).getIndexes(this.projectPath);
            this.indexes = result.indexes;
            this._onDidChangeTreeData.fire();
        } catch (err) {
            console.error('Failed to load indexes:', err);
            this.indexes = [];
            this._onDidChangeTreeData.fire();
        }
    }

    clear(): void {
        this.indexes = [];
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: IndexesTreeElement): vscode.TreeItem {
        return element;
    }

    getChildren(element?: IndexesTreeElement): vscode.ProviderResult<IndexesTreeElement[]> {
        if (element) {
            return [];
        }

        if (!this.projectPath || this.indexes.length === 0) {
            return [new EmptyStateItem('No indexes found')];
        }

        return [...this.indexes]
            .sort((a, b) => a.index_name.localeCompare(b.index_name))
            .map((indexProjection) => new IndexTreeItem(indexProjection, toIndexUri(this.projectPath!, indexProjection.index_name)));
    }
}

class IndexTreeItem extends vscode.TreeItem {
    constructor(
        public readonly indexProjection: IndexProjection,
        public readonly indexUri: vscode.Uri,
    ) {
        super(indexProjection.index_name, vscode.TreeItemCollapsibleState.None);
        this.id = `index:${indexProjection.index_name}`;
        this.contextValue = 'indexProjection';
        this.resourceUri = indexUri;
        this.iconPath = new vscode.ThemeIcon(isIndexStale(indexProjection) ? 'warning' : 'book');
        this.command = {
            command: 'vscode.open',
            title: 'Open Index',
            arguments: [indexUri],
        };

        const entries = indexProjection.entries_json;
        const entryCount = Array.isArray(entries) ? entries.length : null;
        this.description = entryCount === null
            ? (isIndexStale(indexProjection) ? 'stale' : undefined)
            : `${entryCount} entr${entryCount === 1 ? 'y' : 'ies'}${isIndexStale(indexProjection) ? ' · stale' : ''}`;

        this.tooltip = this.buildTooltip(indexProjection, entryCount);
    }

    private buildTooltip(indexProjection: IndexProjection, entryCount: number | null): string {
        const lines = [
            `Index: ${indexProjection.index_name}`,
            ...(entryCount !== null ? [`Entries: ${entryCount}`] : []),
            `Status: ${isIndexStale(indexProjection) ? 'stale' : 'fresh'}`,
            ...(indexProjection.last_refreshed_at
                ? [`Refreshed: ${new Date(indexProjection.last_refreshed_at).toLocaleString()}`]
                : []),
        ];

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
