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

interface StatusVisual {
    label: string;
    icon: string;
    color: string;
    priority: number;
}

const STATUS_VISUALS: Record<string, StatusVisual> = {
    'pending': {
        label: 'PENDING',
        icon: 'clock',
        color: 'editorWarning.foreground',
        priority: 0,
    },
    'escalated': {
        label: 'ESCALATED',
        icon: 'arrow-up',
        color: 'errorForeground',
        priority: 1,
    },
    'discussed': {
        label: 'DISCUSSED',
        icon: 'comment-discussion',
        color: 'editorInfo.foreground',
        priority: 2,
    },
    'revised': {
        label: 'REVISED',
        icon: 'edit',
        color: 'editorInfo.foreground',
        priority: 2,
    },
    'accepted': {
        label: 'ACCEPTED',
        icon: 'check',
        color: 'gitDecoration.addedResourceForeground',
        priority: 3,
    },
    'rejected': {
        label: 'REJECTED',
        icon: 'close',
        color: 'gitDecoration.deletedResourceForeground',
        priority: 3,
    },
    'withdrawn': {
        label: 'WITHDRAWN',
        icon: 'circle-slash',
        color: 'disabledForeground',
        priority: 3,
    },
    'conceded': {
        label: 'CONCEDED',
        icon: 'arrow-right',
        color: 'disabledForeground',
        priority: 3,
    },
};

const DEFAULT_STATUS_VISUAL: StatusVisual = {
    label: 'PENDING',
    icon: 'clock',
    color: 'editorWarning.foreground',
    priority: 0,
};

const SEVERITY_TOKENS: Record<string, string> = {
    'critical': 'CRIT',
    'major': 'MAJ',
    'minor': 'MIN',
};

const SEVERITY_PRIORITY: Record<string, number> = {
    'critical': 0,
    'major': 1,
    'minor': 2,
};

function getNormalizedStatus(status?: string): string {
    return (status || 'pending').toLowerCase();
}

function getStatusVisual(status?: string): StatusVisual {
    return STATUS_VISUALS[getNormalizedStatus(status)] || DEFAULT_STATUS_VISUAL;
}

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
        const currentFindingNumber = this.findings[this.currentIndex]?.number;

        return this.findings
            .map((finding, index) => ({ finding, index }))
            .filter(({ finding }) => finding.lens.toLowerCase() === lens)
            .sort((a, b) => {
                const statusPriority =
                    getStatusVisual(a.finding.status).priority - getStatusVisual(b.finding.status).priority;
                if (statusPriority !== 0) {
                    return statusPriority;
                }

                const severityPriority =
                    (SEVERITY_PRIORITY[a.finding.severity] ?? Number.MAX_SAFE_INTEGER) -
                    (SEVERITY_PRIORITY[b.finding.severity] ?? Number.MAX_SAFE_INTEGER);
                if (severityPriority !== 0) {
                    return severityPriority;
                }

                return a.finding.number - b.finding.number;
            })
            .map(({ finding, index }) =>
                new FindingTreeItem(finding, index, this.scenePath, finding.number === currentFindingNumber),
            );
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
        const statusVisual = getStatusVisual(finding.status);
        const severityToken = SEVERITY_TOKENS[finding.severity] || finding.severity.toUpperCase();
        const lineRange = finding.line_start !== null
            ? finding.line_end !== null && finding.line_end !== finding.line_start
                ? `L${finding.line_start}-L${finding.line_end}`
                : `L${finding.line_start}`
            : '';

        const label = `${isCurrent ? '▶ ' : ''}${statusVisual.label} [${severityToken}] #${finding.number}`;
        super(label, vscode.TreeItemCollapsibleState.None);

        this.finding = finding;
        this.findingIndex = index;
        const preview = finding.evidence.slice(0, 60) || finding.location;
        this.description = lineRange
            ? `${lineRange} — ${preview}`
            : finding.evidence.slice(0, 80) || finding.location;
        this.tooltip = this.buildTooltip(finding);
        this.iconPath = new vscode.ThemeIcon(statusVisual.icon, new vscode.ThemeColor(statusVisual.color));
        this.contextValue = 'finding';

        // Highlight current finding while preserving the status icon cue.
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
        const status = getNormalizedStatus(finding.status);
        const md = new vscode.MarkdownString();
        md.appendMarkdown(`**#${finding.number} — ${finding.severity.toUpperCase()}** (${finding.lens})\n\n`);
        md.appendMarkdown(`**Status:** ${status}\n\n`);
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
        return md;
    }
}
