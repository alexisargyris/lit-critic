/**
 * Findings Tree View — sidebar panel showing all findings in a navigable tree.
 *
 * Tree structure:
 *   ▼ Prose (3 findings)
 *       ⚠️ #1 Major — Rhythm break at L042-L045    [pending]
 *       ℹ️ #3 Minor — Passive voice at L078         [accepted ✓]
 *   ▼ Structure (2 findings)
 *       🔴 #2 Critical — Missing scene goal          [pending]
 *
 * Click navigates to the line in the editor.
 */

import * as vscode from 'vscode';
import { Finding } from './types';

// Icons by severity
const SEVERITY_ICONS: Record<string, vscode.ThemeIcon> = {
    'critical': new vscode.ThemeIcon('error', new vscode.ThemeColor('errorForeground')),
    'major': new vscode.ThemeIcon('warning', new vscode.ThemeColor('editorWarning.foreground')),
    'minor': new vscode.ThemeIcon('info', new vscode.ThemeColor('editorInfo.foreground')),
};

// Status suffixes
const STATUS_SUFFIX: Record<string, string> = {
    'pending': '',
    'accepted': ' ✓',
    'rejected': ' ✗',
    'revised': ' ✎',
    'withdrawn': ' ⊘',
    'escalated': ' ⬆',
    'discussed': ' 💬',
};

export class FindingsTreeProvider implements vscode.TreeDataProvider<FindingTreeItem | LensGroupItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<FindingTreeItem | LensGroupItem | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private findings: Finding[] = [];
    private scenePath: string | null = null;
    private currentIndex: number = -1;

    /**
     * Update the findings list and refresh the tree.
     */
    setFindings(findings: Finding[], scenePath: string, currentIndex: number = -1): void {
        this.findings = findings;
        this.scenePath = scenePath;
        this.currentIndex = currentIndex;
        this._onDidChangeTreeData.fire();
    }

    /**
     * Update the current finding index (highlight which one is active).
     */
    setCurrentIndex(index: number): void {
        this.currentIndex = index;
        this._onDidChangeTreeData.fire();
    }

    /**
     * Update a single finding in the list (after status change).
     */
    updateFinding(finding: Finding): void {
        const idx = this.findings.findIndex(f => f.number === finding.number);
        if (idx >= 0) {
            this.findings[idx] = finding;
            this._onDidChangeTreeData.fire();
        }
    }

    /**
     * Clear all findings.
     */
    clear(): void {
        this.findings = [];
        this.scenePath = null;
        this.currentIndex = -1;
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: FindingTreeItem | LensGroupItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: FindingTreeItem | LensGroupItem): (FindingTreeItem | LensGroupItem)[] {
        if (!element) {
            // Root level — group by lens
            return this.getLensGroups();
        }

        if (element instanceof LensGroupItem) {
            // Lens group — show findings for that lens
            return this.getFindingsForLens(element.lens);
        }

        return [];
    }

    private getLensGroups(): LensGroupItem[] {
        const groups = new Map<string, Finding[]>();

        for (const finding of this.findings) {
            const lens = finding.lens.toLowerCase();
            if (!groups.has(lens)) {
                groups.set(lens, []);
            }
            groups.get(lens)!.push(finding);
        }

        // Order: prose, structure, logic, clarity, continuity
        const order = ['prose', 'structure', 'logic', 'clarity', 'continuity'];
        const result: LensGroupItem[] = [];

        for (const lens of order) {
            const findings = groups.get(lens);
            if (findings && findings.length > 0) {
                result.push(new LensGroupItem(lens, findings.length));
            }
        }

        // Any remaining lenses not in the standard order
        for (const [lens, findings] of groups) {
            if (!order.includes(lens) && findings.length > 0) {
                result.push(new LensGroupItem(lens, findings.length));
            }
        }

        return result;
    }

    private getFindingsForLens(lens: string): FindingTreeItem[] {
        return this.findings
            .filter(f => f.lens.toLowerCase() === lens)
            .map(f => {
                const idx = this.findings.indexOf(f);
                return new FindingTreeItem(f, idx, this.scenePath, f.number === this.findings[this.currentIndex]?.number);
            });
    }
}

/**
 * Tree item representing a lens group (parent node).
 */
export class LensGroupItem extends vscode.TreeItem {
    readonly lens: string;

    constructor(lens: string, count: number) {
        const label = `${lens.charAt(0).toUpperCase() + lens.slice(1)} (${count})`;
        super(label, vscode.TreeItemCollapsibleState.Expanded);
        this.lens = lens;
        this.iconPath = new vscode.ThemeIcon('symbol-namespace');
        this.contextValue = 'lensGroup';
    }
}

/**
 * Tree item representing a single finding (leaf node).
 *
 * Clicking a finding in the tree fires `literaryCritic.selectFinding`,
 * which navigates to the line in the editor AND opens the Discussion
 * Panel for that finding — regardless of the sequential review order.
 */
export class FindingTreeItem extends vscode.TreeItem {
    readonly finding: Finding;
    /** Index of this finding in the flat findings array. */
    readonly findingIndex: number;

    constructor(finding: Finding, index: number, scenePath: string | null, isCurrent: boolean) {
        const status = finding.status || 'pending';
        const suffix = STATUS_SUFFIX[status] || '';
        const lineRange = finding.line_start !== null
            ? finding.line_end !== null && finding.line_end !== finding.line_start
                ? `L${finding.line_start}-L${finding.line_end}`
                : `L${finding.line_start}`
            : '';

        const label = `#${finding.number} ${finding.severity}${suffix}`;
        super(label, vscode.TreeItemCollapsibleState.None);

        this.finding = finding;
        this.findingIndex = index;
        this.description = lineRange
            ? `${lineRange} — ${finding.evidence.slice(0, 60)}`
            : finding.evidence.slice(0, 80) || finding.location;
        this.tooltip = this.buildTooltip(finding);
        this.iconPath = SEVERITY_ICONS[finding.severity] || SEVERITY_ICONS['major'];
        this.contextValue = 'finding';

        // Highlight current finding
        if (isCurrent) {
            this.description = `▶ ${this.description}`;
        }

        // Click opens the discussion panel for this finding (and navigates to its line)
        this.command = {
            command: 'literaryCritic.selectFinding',
            title: 'Select finding',
            arguments: [index],
        };
    }

    private buildTooltip(finding: Finding): vscode.MarkdownString {
        const md = new vscode.MarkdownString();
        md.appendMarkdown(`**#${finding.number} — ${finding.severity.toUpperCase()}** (${finding.lens})\n\n`);
        md.appendMarkdown(`${finding.evidence}\n\n`);
        if (finding.impact) {
            md.appendMarkdown(`**Impact:** ${finding.impact}\n\n`);
        }
        if (finding.options && finding.options.length > 0) {
            md.appendMarkdown('**Suggestions:**\n');
            for (const opt of finding.options) {
                md.appendMarkdown(`- ${opt}\n`);
            }
        }
        if (finding.status && finding.status !== 'pending') {
            md.appendMarkdown(`\n**Status:** ${finding.status}`);
        }
        return md;
    }
}
