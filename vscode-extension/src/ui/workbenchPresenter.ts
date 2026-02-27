import * as vscode from 'vscode';

import { DiagnosticsProvider } from '../diagnosticsProvider';
import { FindingsTreeProvider } from '../findingsTreeProvider';
import { SessionsTreeProvider } from '../sessionsTreeProvider';
import { StatusBar } from '../statusBar';
import { DiscussionPanel } from '../discussionPanel';
import {
    DiscussionContextTransition,
    Finding,
    IndexChangeReport,
    SceneChangeReport,
} from '../types';

export interface WorkbenchPresenterDeps {
    statusBar: StatusBar;
    diagnosticsProvider: DiagnosticsProvider;
    findingsTreeProvider: FindingsTreeProvider;
    sessionsTreeProvider: SessionsTreeProvider;
    ensureDiscussionPanel: () => DiscussionPanel;
    getDiscussionPanel: () => DiscussionPanel | undefined;
}

export class WorkbenchPresenter {
    private findingsTreeView: vscode.TreeView<any> | undefined;
    private sessionsTreeView: vscode.TreeView<any> | undefined;

    constructor(private readonly deps: WorkbenchPresenterDeps) {}

    bindTreeViews(findingsTreeView: vscode.TreeView<any>, sessionsTreeView: vscode.TreeView<any>): void {
        this.findingsTreeView = findingsTreeView;
        this.sessionsTreeView = sessionsTreeView;
    }

    setReady(): void {
        this.deps.statusBar.setReady();
    }

    setAnalyzing(message?: string): void {
        this.deps.statusBar.setAnalyzing(message);
    }

    setProgress(current: number, total: number): void {
        this.deps.statusBar.setProgress(current, total);
    }

    setComplete(): void {
        this.deps.statusBar.setComplete();
    }

    setError(message: string): void {
        this.deps.statusBar.setError(message);
    }

    showDiscussion(
        finding: Finding,
        current: number,
        total: number,
        isAmbiguity: boolean,
        transition?: DiscussionContextTransition,
        closedSessionNotice?: string,
    ): void {
        this.deps.ensureDiscussionPanel().show(
            finding,
            current,
            total,
            isAmbiguity,
            transition,
            closedSessionNotice,
        );
    }

    notifySceneChange(report: SceneChangeReport): void {
        this.deps.ensureDiscussionPanel().notifySceneChange(report);
    }

    notifyIndexChange(report: IndexChangeReport): void {
        this.deps.ensureDiscussionPanel().notifyIndexChange(report);
    }

    clearIndexChangeNotice(): void {
        this.deps.ensureDiscussionPanel().clearIndexChangeNotice();
    }

    closeDiscussion(): void {
        this.deps.getDiscussionPanel()?.close();
    }

    setFindingsPresentation(findings: Finding[], scenePath: string, currentIndex: number, scenePaths?: string[]): void {
        this.deps.findingsTreeProvider.setFindings(findings, scenePath, currentIndex);
        this.revealCurrentFindingSelection();
        this.deps.diagnosticsProvider.setScenePath(scenePath, scenePaths);
    }

    setCurrentFindingIndex(index: number): void {
        this.deps.findingsTreeProvider.setCurrentIndex(index);
        this.revealCurrentFindingSelection();
    }

    updateFindingPresentation(finding: Finding, allFindings: Finding[]): void {
        this.deps.findingsTreeProvider.updateFinding(finding);
        this.deps.diagnosticsProvider.updateFromFindings(allFindings);
    }

    removeFindingDiagnostic(findingNumber: number): void {
        this.deps.diagnosticsProvider.removeFinding(findingNumber);
    }

    updateSingleFindingDiagnostic(finding: Finding): void {
        this.deps.diagnosticsProvider.updateSingleFinding(finding);
    }

    updateDiagnosticsFromFindings(allFindings: Finding[]): void {
        this.deps.diagnosticsProvider.updateFromFindings(allFindings);
    }

    clearSessionPresentation(): void {
        this.deps.diagnosticsProvider.clear();
        this.deps.findingsTreeProvider.clear();
        this.deps.statusBar.setReady();
    }

    revealCurrentFindingSelection(): void {
        const item = this.deps.findingsTreeProvider.getCurrentFindingItem?.();
        if (!this.findingsTreeView || typeof this.findingsTreeView.reveal !== 'function' || !item) {
            return;
        }

        const revealResult = this.findingsTreeView.reveal(item, {
            select: true,
            focus: false,
            expand: true,
        });
        void Promise.resolve(revealResult).catch(() => {
            // Non-fatal: tree may not be visible/materialized yet.
        });
    }

    revealCurrentSessionSelection(): void {
        const item = this.deps.sessionsTreeProvider.getCurrentSessionItem?.();
        if (!this.sessionsTreeView || typeof this.sessionsTreeView.reveal !== 'function' || !item) {
            return;
        }

        const revealResult = this.sessionsTreeView.reveal(item, {
            select: true,
            focus: false,
            expand: true,
        });
        void Promise.resolve(revealResult).catch(() => {
            // Non-fatal: tree may not be visible/materialized yet.
        });
    }
}
