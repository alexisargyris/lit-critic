/**
 * Learning Tree Provider — sidebar view for managing learning data.
 *
 * Shows:
 * - Preferences
 * - Blind Spots
 * - Resolutions
 * - Ambiguity (Intentional / Accidental)
 *
 * Actions:
 * - Delete entry (context menu)
 * - Export LEARNING.md (toolbar)
 * - Reset all learning data (toolbar)
 */

import * as vscode from 'vscode';
import { ApiClient } from './apiClient';
import { LearningData } from './types';

type LearningTreeElement = LearningCategoryItem | LearningEntryItem;

export class LearningTreeProvider implements vscode.TreeDataProvider<LearningTreeElement> {
    private _onDidChangeTreeData = new vscode.EventEmitter<LearningTreeElement | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private learning: LearningData | null = null;
    private projectPath: string | null = null;
    private apiClient: ApiClient | null = null;

    constructor() {}

    setApiClient(client: ApiClient): void {
        this.apiClient = client;
    }

    setProjectPath(projectPath: string): void {
        this.projectPath = projectPath;
    }

    async refresh(): Promise<void> {
        if (!this.apiClient || !this.projectPath) {
            this.learning = null;
            this._onDidChangeTreeData.fire();
            return;
        }

        try {
            this.learning = await this.apiClient.getLearning(this.projectPath);
            this._onDidChangeTreeData.fire();
        } catch (err) {
            console.error('Failed to load learning data:', err);
            this.learning = null;
            this._onDidChangeTreeData.fire();
        }
    }

    clear(): void {
        this.learning = null;
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: LearningTreeElement): vscode.TreeItem {
        return element;
    }

    getChildren(element?: LearningTreeElement): vscode.ProviderResult<LearningTreeElement[]> {
        if (!this.learning) {
            return [];
        }

        if (!element) {
            // Root level — show categories
            const categories: LearningTreeElement[] = [];

            if (this.learning.preferences.length > 0) {
                categories.push(new LearningCategoryItem(
                    'Preferences',
                    this.learning.preferences.length,
                    'preferences',
                    'symbol-variable'
                ));
            }

            if (this.learning.blind_spots.length > 0) {
                categories.push(new LearningCategoryItem(
                    'Blind Spots',
                    this.learning.blind_spots.length,
                    'blind_spots',
                    'eye-closed'
                ));
            }

            if (this.learning.resolutions.length > 0) {
                categories.push(new LearningCategoryItem(
                    'Resolutions',
                    this.learning.resolutions.length,
                    'resolutions',
                    'check-all'
                ));
            }

            if (this.learning.ambiguity_intentional.length > 0) {
                categories.push(new LearningCategoryItem(
                    'Ambiguity — Intentional',
                    this.learning.ambiguity_intentional.length,
                    'ambiguity_intentional',
                    'question'
                ));
            }

            if (this.learning.ambiguity_accidental.length > 0) {
                categories.push(new LearningCategoryItem(
                    'Ambiguity — Accidental',
                    this.learning.ambiguity_accidental.length,
                    'ambiguity_accidental',
                    'warning'
                ));
            }

            if (categories.length === 0) {
                return [new LearningEntryItem('No learning data yet', undefined, 'empty')];
            }

            return categories;
        }

        // Return entries for a category
        if (element instanceof LearningCategoryItem) {
            const entries = this.getEntriesForCategory(element.category);
            return entries.map(e => new LearningEntryItem(
                e.description,
                e.id,
                element.category
            ));
        }

        return [];
    }

    private getEntriesForCategory(category: string): Array<{ id?: number; description: string }> {
        if (!this.learning) {
            return [];
        }

        switch (category) {
            case 'preferences':
                return this.learning.preferences;
            case 'blind_spots':
                return this.learning.blind_spots;
            case 'resolutions':
                return this.learning.resolutions;
            case 'ambiguity_intentional':
                return this.learning.ambiguity_intentional;
            case 'ambiguity_accidental':
                return this.learning.ambiguity_accidental;
            default:
                return [];
        }
    }
}

class LearningCategoryItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly count: number,
        public readonly category: string,
        iconName: string
    ) {
        super(label, vscode.TreeItemCollapsibleState.Collapsed);
        this.contextValue = 'learningCategory';
        this.description = `${count}`;
        this.iconPath = new vscode.ThemeIcon(iconName);
    }
}

class LearningEntryItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly entryId: number | undefined,
        public readonly category: string
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);

        if (entryId !== undefined) {
            this.contextValue = 'learningEntry';
            this.iconPath = new vscode.ThemeIcon('circle-small');
            this.tooltip = label;
        } else {
            this.contextValue = 'empty';
            this.iconPath = new vscode.ThemeIcon('info');
        }
    }
}
