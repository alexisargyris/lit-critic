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

const FINDING_URI_SCHEME = 'lit-critic-finding';
const TREE_COUNT_URI_SCHEME = 'lit-critic-count';

const LENS_ICONS: Record<string, string> = {
    prose: 'whole-word',
    structure: 'list-tree',
    logic: 'lightbulb',
    clarity: 'eye',
    continuity: 'git-compare',
};

const RESOLVED_COLOR_ID = 'gitDecoration.ignoredResourceForeground';

interface StatusVisual {
    priority: number;
}

const STATUS_VISUALS: Record<string, StatusVisual> = {
    'pending': {
        priority: 0,
    },
    'escalated': {
        priority: 1,
    },
    'discussed': {
        priority: 2,
    },
    'revised': {
        priority: 2,
    },
    'accepted': {
        priority: 3,
    },
    'rejected': {
        priority: 3,
    },
    'withdrawn': {
        priority: 3,
    },
    'conceded': {
        priority: 3,
    },
};

const DEFAULT_STATUS_VISUAL: StatusVisual = {
    priority: 0,
};

const SEVERITY_COLORS: Record<string, string> = {
    'critical': 'charts.red',
    'major': 'charts.yellow',
    'minor': 'charts.blue',
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

function getNormalizedSeverity(severity?: string): string {
    return (severity || '').toLowerCase();
}

function isActiveStatus(status?: string): boolean {
    const normalized = getNormalizedStatus(status);
    return normalized === 'pending' || normalized === 'escalated' || normalized === 'discussed' || normalized === 'revised';
}

function getSeverityColorId(severity?: string): string {
    return SEVERITY_COLORS[getNormalizedSeverity(severity)] || 'charts.blue';
}

function getLabelColorForFinding(status?: string, severity?: string): string | undefined {
    if (!isActiveStatus(status)) {
        return RESOLVED_COLOR_ID;
    }

    const normalizedSeverity = getNormalizedSeverity(severity);
    if (normalizedSeverity === 'critical') {
        return 'charts.red';
    }
    if (normalizedSeverity === 'major') {
        return 'charts.yellow';
    }

    return undefined;
}

function getResolvedIcon(status?: string): vscode.ThemeIcon {
    const dimColor = new vscode.ThemeColor(RESOLVED_COLOR_ID);
    const resolvedStatus = getNormalizedStatus(status);
    const iconByStatus: Record<string, string> = {
        accepted: 'pass',
        rejected: 'close',
        withdrawn: 'dash',
        conceded: 'check',
    };
    const iconId = iconByStatus[resolvedStatus] || 'circle-outline';
    return new vscode.ThemeIcon(iconId, dimColor);
}

function getActiveIcon(severity?: string): vscode.ThemeIcon {
    const normalizedSeverity = getNormalizedSeverity(severity);
    const iconBySeverity: Record<string, string> = {
        critical: 'error',
        major: 'warning',
        minor: 'info',
    };
    const iconId = iconBySeverity[normalizedSeverity] || 'info';
    return new vscode.ThemeIcon(iconId, new vscode.ThemeColor(getSeverityColorId(severity)));
}

function getFindingIcon(finding: Finding): vscode.ThemeIcon {
    if (!isActiveStatus(finding.status)) {
        return getResolvedIcon(finding.status);
    }
    return getActiveIcon(finding.severity);
}

function buildFindingUri(finding: Finding): vscode.Uri {
    const status = encodeURIComponent(getNormalizedStatus(finding.status));
    const severity = encodeURIComponent(getNormalizedSeverity(finding.severity) || 'minor');
    return vscode.Uri.parse(
        `${FINDING_URI_SCHEME}://f/${finding.number}?status=${status}&severity=${severity}`,
    );
}

function getMaxActiveSeverity(findings: Finding[]): string {
    const activeFindings = findings.filter((finding) => isActiveStatus(finding.status));
    if (activeFindings.some((finding) => getNormalizedSeverity(finding.severity) === 'critical')) {
        return 'critical';
    }
    if (activeFindings.some((finding) => getNormalizedSeverity(finding.severity) === 'major')) {
        return 'major';
    }
    return 'minor';
}

function buildLensUri(lens: string, activeCount: number, total: number, maxSeverity: string): vscode.Uri {
    const encodedLens = encodeURIComponent(lens);
    const encodedSeverity = encodeURIComponent(getNormalizedSeverity(maxSeverity) || 'minor');
    return vscode.Uri.parse(
        `${FINDING_URI_SCHEME}://lens/${encodedLens}?active=${activeCount}&total=${total}&maxSeverity=${encodedSeverity}`,
    );
}

function toThemeColor(colorId?: string): vscode.ThemeColor | undefined {
    return colorId ? new vscode.ThemeColor(colorId) : undefined;
}

export class FindingsDecorationProvider implements vscode.FileDecorationProvider {
    private readonly _onDidChange = new vscode.EventEmitter<vscode.Uri | vscode.Uri[] | undefined>();
    readonly onDidChangeFileDecorations = this._onDidChange.event;

    fireChange(): void {
        this._onDidChange.fire(undefined);
    }

    provideFileDecoration(uri: vscode.Uri): vscode.FileDecoration | undefined {
        if (uri.scheme === TREE_COUNT_URI_SCHEME) {
            const params = new URLSearchParams(uri.query);
            return this.decorateCount(params);
        }

        if (uri.scheme !== FINDING_URI_SCHEME) {
            return undefined;
        }

        const params = new URLSearchParams(uri.query);

        if (uri.authority === 'f') {
            return this.decorateFinding(params);
        }

        if (uri.authority === 'lens') {
            return this.decorateLens(params);
        }

        return undefined;
    }

    private decorateFinding(params: URLSearchParams): vscode.FileDecoration | undefined {
        const status = getNormalizedStatus(params.get('status') || 'pending');
        const severity = getNormalizedSeverity(params.get('severity') || 'minor');
        const labelColorId = getLabelColorForFinding(status, severity);
        const color = toThemeColor(labelColorId);

        if (status === 'pending') {
            return {
                color,
                tooltip: 'Pending',
            };
        }

        const badges: Record<string, string> = {
            escalated: '!!',
            discussed: 'D',
            revised: 'R',
            accepted: '✓',
            rejected: '✗',
            withdrawn: 'W',
            conceded: 'C',
        };

        const tooltips: Record<string, string> = {
            escalated: 'Escalated',
            discussed: 'Discussed',
            revised: 'Revised',
            accepted: 'Accepted',
            rejected: 'Rejected',
            withdrawn: 'Withdrawn',
            conceded: 'Conceded',
        };

        return {
            badge: badges[status],
            color,
            tooltip: tooltips[status] || status,
        };
    }

    private decorateLens(params: URLSearchParams): vscode.FileDecoration | undefined {
        const active = Number.parseInt(params.get('active') || '0', 10);
        const total = Number.parseInt(params.get('total') || '0', 10);
        const maxSeverity = getNormalizedSeverity(params.get('maxSeverity') || 'minor');
        const colorId = active > 0 ? getSeverityColorId(maxSeverity) : undefined;

        return {
            badge: String(Math.max(0, total)),
            color: toThemeColor(colorId),
            tooltip: `${Math.max(0, total)} finding${total === 1 ? '' : 's'} (${Math.max(0, active)} active)`,
        };
    }

    private decorateCount(params: URLSearchParams): vscode.FileDecoration | undefined {
        const count = Number.parseInt(params.get('count') || '0', 10);
        return {
            badge: String(Math.max(0, count)),
            tooltip: `${Math.max(0, count)} total`,
        };
    }
}

export class FindingsTreeProvider implements vscode.TreeDataProvider<FindingTreeItem | LensGroupItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<FindingTreeItem | LensGroupItem | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private findings: Finding[] = [];
    private scenePath: string | null = null;
    private currentIndex: number = -1;
    private cacheDirty = true;
    private lensItems: LensGroupItem[] = [];
    private findingItemsByLens: Map<string, FindingTreeItem[]> = new Map();
    private findingItemsByIndex: Map<number, FindingTreeItem> = new Map();

    constructor(private readonly decorationProvider?: FindingsDecorationProvider) {}

    private notifyTreeChanged(): void {
        this.cacheDirty = true;
        this._onDidChangeTreeData.fire();
        this.decorationProvider?.fireChange();
    }

    getCurrentFindingItem(): FindingTreeItem | undefined {
        this.ensureCache();
        return this.findingItemsByIndex.get(this.currentIndex);
    }

    /**
     * Update the findings list and refresh the tree.
     */
    setFindings(findings: Finding[], scenePath: string, currentIndex: number = -1): void {
        this.findings = findings;
        this.scenePath = scenePath;
        this.currentIndex = currentIndex;
        this.notifyTreeChanged();
    }

    /**
     * Update the current finding index (highlight which one is active).
     */
    setCurrentIndex(index: number): void {
        this.currentIndex = index;
        this.notifyTreeChanged();
    }

    /**
     * Update a single finding in the list (after status change).
     */
    updateFinding(finding: Finding): void {
        const idx = this.findings.findIndex(f => f.number === finding.number);
        if (idx >= 0) {
            this.findings[idx] = finding;
            this.notifyTreeChanged();
        }
    }

    /**
     * Clear all findings.
     */
    clear(): void {
        this.findings = [];
        this.scenePath = null;
        this.currentIndex = -1;
        this.notifyTreeChanged();
    }

    getTreeItem(element: FindingTreeItem | LensGroupItem): vscode.TreeItem {
        return element;
    }

    getParent(element: FindingTreeItem | LensGroupItem): LensGroupItem | undefined {
        this.ensureCache();
        if (element instanceof LensGroupItem) {
            return undefined;
        }
        // FindingTreeItem — return its parent LensGroupItem
        const lens = element.finding.lens.toLowerCase();
        return this.lensItems.find((item) => item.lens === lens);
    }

    getChildren(element?: FindingTreeItem | LensGroupItem): (FindingTreeItem | LensGroupItem)[] {
        this.ensureCache();

        if (!element) {
            // Root level — group by lens
            return this.lensItems;
        }

        if (element instanceof LensGroupItem) {
            // Lens group — show findings for that lens
            return this.findingItemsByLens.get(element.lens) || [];
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
        const lensItems: LensGroupItem[] = [];
        const findingItemsByLens = new Map<string, FindingTreeItem[]>();
        const findingItemsByIndex = new Map<number, FindingTreeItem>();

        const currentFindingNumber = this.findings[this.currentIndex]?.number;

        const createLensAndFindings = (lens: string, findings: Finding[]): void => {
            if (!findings || findings.length === 0) {
                return;
            }

            const activeCount = findings.filter((finding) => isActiveStatus(finding.status)).length;
            const maxSeverity = getMaxActiveSeverity(findings);
            lensItems.push(new LensGroupItem(lens, findings.length, activeCount, maxSeverity));

            const findingItems = this.findings
                .map((finding, index) => ({ finding, index }))
                .filter(({ finding }) => finding.lens.toLowerCase() === lens)
                .sort((a, b) => {
                    const statusPriority =
                        getStatusVisual(a.finding.status).priority - getStatusVisual(b.finding.status).priority;
                    if (statusPriority !== 0) {
                        return statusPriority;
                    }

                    const severityPriority =
                        (SEVERITY_PRIORITY[getNormalizedSeverity(a.finding.severity)] ?? Number.MAX_SAFE_INTEGER) -
                        (SEVERITY_PRIORITY[getNormalizedSeverity(b.finding.severity)] ?? Number.MAX_SAFE_INTEGER);
                    if (severityPriority !== 0) {
                        return severityPriority;
                    }

                    return a.finding.number - b.finding.number;
                })
                .map(({ finding, index }) => {
                    const item = new FindingTreeItem(
                        finding,
                        index,
                        this.scenePath,
                        finding.number === currentFindingNumber,
                    );
                    findingItemsByIndex.set(index, item);
                    return item;
                });

            findingItemsByLens.set(lens, findingItems);
        };

        for (const lens of order) {
            const findings = groups.get(lens);
            createLensAndFindings(lens, findings || []);
        }

        // Any remaining lenses not in the standard order
        for (const [lens, findings] of groups) {
            if (!order.includes(lens) && findings.length > 0) {
                createLensAndFindings(lens, findings);
            }
        }

        this.lensItems = lensItems;
        this.findingItemsByLens = findingItemsByLens;
        this.findingItemsByIndex = findingItemsByIndex;
        this.cacheDirty = false;
    }
}

/**
 * Tree item representing a lens group (parent node).
 */
export class LensGroupItem extends vscode.TreeItem {
    readonly lens: string;

    constructor(lens: string, count: number, activeCount: number, maxSeverity: string) {
        const label = `${lens.charAt(0).toUpperCase() + lens.slice(1)}`;
        super(label, vscode.TreeItemCollapsibleState.Expanded);
        this.lens = lens;
        this.iconPath = new vscode.ThemeIcon(LENS_ICONS[lens] || 'symbol-namespace');
        this.contextValue = 'lensGroup';
        this.resourceUri = buildLensUri(lens, activeCount, count, maxSeverity);
        this.id = `lens:${lens}`;
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
        const lineRange = finding.line_start !== null
            ? finding.line_end !== null && finding.line_end !== finding.line_start
                ? `L${finding.line_start}-L${finding.line_end}`
                : `L${finding.line_start}`
            : '';

        const label = `#${finding.number}${lineRange ? ` ${lineRange}` : ''}`;
        super(label, vscode.TreeItemCollapsibleState.None);

        this.finding = finding;
        this.findingIndex = index;
        const preview = finding.evidence.slice(0, 60) || finding.location;
        this.description = isCurrent ? `${preview} · current` : preview;
        this.tooltip = this.buildTooltip(finding);
        this.iconPath = getFindingIcon(finding);
        this.contextValue = 'finding';
        this.resourceUri = buildFindingUri(finding);
        this.id = `finding:${finding.number}`;

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
