/**
 * Status Bar — quick status overview in the VS Code status bar.
 *
 * States:
 *   Ready                              — no active session
 *   $(sync~spin) Analyzing...          — analysis in progress
 *   📖 3/12 findings reviewed          — active session
 *   📖 Complete                        — all findings processed
 */

import * as vscode from 'vscode';

export class StatusBar implements vscode.Disposable {
    private item: vscode.StatusBarItem;

    constructor() {
        this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
        this.item.command = 'literaryCritic.analyze';
        this.setReady();
        this.item.show();
    }

    /** No active session. */
    setReady(): void {
        this.item.text = '$(book) lit-critic';
        this.item.tooltip = 'lit-critic ready';
        this.item.backgroundColor = undefined;
        this.item.command = undefined;
    }

    /** Analysis is running. */
    setAnalyzing(message?: string): void {
        const busyMessage = message || 'Analyzing...';
        this.item.text = `$(sync~spin) lit-critic: ${busyMessage}`;
        this.item.tooltip = `${busyMessage} · lit-critic is busy — please wait.`;
        this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        this.item.command = undefined;
    }

    /** Active session — show progress. */
    setProgress(current: number, total: number): void {
        this.item.text = `$(book) ${current}/${total} findings`;
        this.item.tooltip = `lit-critic: ${current} of ${total} findings reviewed`;
        this.item.backgroundColor = undefined;
        this.item.command = undefined;
    }

    /** All findings processed. */
    setComplete(): void {
        this.item.text = '$(book) Review complete';
        this.item.tooltip = 'All findings have been reviewed';
        this.item.backgroundColor = undefined;
        this.item.command = undefined;
    }

    /** Server error or not running. */
    setError(message: string): void {
        this.item.text = '$(error) lit-critic';
        this.item.tooltip = message;
        this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
        this.item.command = undefined;
    }

    dispose(): void {
        this.item.dispose();
    }
}
