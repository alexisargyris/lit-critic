/**
 * Real tests for FindingsTreeProvider module.
 */

import { strict as assert } from 'assert';
import { createFreshMockVscode, sampleFindings } from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

declare const describe: (name: string, fn: () => void) => void;
declare const beforeEach: (fn: () => void) => void;
declare const it: (name: string, fn: () => Promise<void> | void) => void;

describe('FindingsTreeProvider (Real)', () => {
    let FindingsTreeProvider: any;
    let FindingsDecorationProvider: any;
    let LensGroupItem: any;
    let FindingTreeItem: any;
    let mockVscode: any;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();

        const module = proxyquire('../../vscode-extension/src/findingsTreeProvider', {
            vscode: mockVscode,
        });

        FindingsTreeProvider = module.FindingsTreeProvider;
        FindingsDecorationProvider = module.FindingsDecorationProvider;
        LensGroupItem = module.LensGroupItem;
        FindingTreeItem = module.FindingTreeItem;
    });

    it('formats finding label and marks current finding in description', () => {
        const provider = new FindingsTreeProvider();
        provider.setFindings([sampleFindings[0]], '/test/scene.txt', 0);

        const group = provider.getChildren()[0];
        const finding = provider.getChildren(group)[0];

        assert.equal(finding.label, '#1 L42-L45');
        assert.ok(String(finding.description).includes('· current'));
        assert.ok(!String(finding.description).includes('▶'));
    });

    it('keeps non-current finding description as plain preview text', () => {
        const provider = new FindingsTreeProvider();
        provider.setFindings(sampleFindings, '/test/scene.txt', 1);

        const proseGroup = provider.getChildren().find((g: any) => g.lens === 'prose');
        const proseFindings = provider.getChildren(proseGroup);
        const nonCurrent = proseFindings.find((f: any) => f.finding.number === 1);

        assert.ok(nonCurrent, 'Expected non-current finding item');
        assert.ok(!String(nonCurrent.description).includes('· current'));
        assert.ok(!String(nonCurrent.description).includes('▶'));
    });

    it('returns current finding item for native TreeView reveal', () => {
        const provider = new FindingsTreeProvider();
        provider.setFindings(sampleFindings, '/test/scene.txt', 1);

        const current = provider.getCurrentFindingItem();

        assert.ok(current, 'Expected current finding item');
        assert.equal(current.findingIndex, 1);
        assert.equal(current.id, 'finding:2');
    });

    it('uses lens-specific icons and lens resource URI metadata', () => {
        const provider = new FindingsTreeProvider();
        provider.setFindings(sampleFindings, '/test/scene.txt', 0);

        const groups = provider.getChildren();
        const prose = groups.find((g: any) => g.lens === 'prose');
        const structure = groups.find((g: any) => g.lens === 'structure');

        assert.equal(prose.iconPath.id, 'whole-word');
        assert.equal(structure.iconPath.id, 'list-tree');
        assert.equal(prose.resourceUri.scheme, 'lit-critic-finding');
        assert.equal(prose.resourceUri.authority, 'lens');
        assert.match(prose.resourceUri.query, /active=1/);
        assert.match(prose.resourceUri.query, /maxSeverity=major/);
    });

    it('uses severity/status-specific finding icons and finding resource URI metadata', () => {
        const provider = new FindingsTreeProvider();
        const findings = [
            { ...sampleFindings[0], status: 'pending', severity: 'major', number: 11, lens: 'prose' },
            { ...sampleFindings[0], status: 'accepted', severity: 'critical', number: 12, lens: 'prose' },
        ];
        provider.setFindings(findings, '/test/scene.txt', -1);

        const proseGroup = provider.getChildren().find((g: any) => g.lens === 'prose');
        const proseFindings = provider.getChildren(proseGroup);

        const pending = proseFindings.find((f: any) => f.finding.number === 11);
        const accepted = proseFindings.find((f: any) => f.finding.number === 12);

        assert.equal(pending.iconPath.id, 'warning');
        assert.equal(pending.iconPath.color.id, 'charts.yellow');
        assert.equal(accepted.iconPath.id, 'pass');
        assert.equal(accepted.iconPath.color.id, 'gitDecoration.ignoredResourceForeground');

        assert.equal(pending.resourceUri.scheme, 'lit-critic-finding');
        assert.equal(pending.resourceUri.authority, 'f');
        assert.match(pending.resourceUri.query, /status=pending/);
        assert.match(pending.resourceUri.query, /severity=major/);
    });

    it('fires decoration updates when tree data changes', () => {
        let fired = 0;
        const provider = new FindingsTreeProvider({ fireChange: () => { fired += 1; } });

        provider.setFindings(sampleFindings, '/test/scene.txt', 0);
        provider.setCurrentIndex(1);
        provider.updateFinding({ ...sampleFindings[0], status: 'accepted' });
        provider.clear();

        assert.ok(fired >= 4);
    });

    it('provides expected status/severity decorations for finding URIs', () => {
        const decorations = new FindingsDecorationProvider();

        const escalated = decorations.provideFileDecoration(
            mockVscode.Uri.parse('lit-critic-finding://f/1?status=escalated&severity=critical'),
        );
        assert.equal(escalated.badge, '!!');
        assert.equal(escalated.color.id, 'charts.red');

        const accepted = decorations.provideFileDecoration(
            mockVscode.Uri.parse('lit-critic-finding://f/2?status=accepted&severity=major'),
        );
        assert.equal(accepted.badge, '✓');
        assert.equal(accepted.color.id, 'gitDecoration.ignoredResourceForeground');

        const pendingMinor = decorations.provideFileDecoration(
            mockVscode.Uri.parse('lit-critic-finding://f/3?status=pending&severity=minor'),
        );
        assert.equal(pendingMinor.badge, undefined);
        assert.equal(pendingMinor.color, undefined);
    });

    it('provides expected lens decorations and ignores unknown URI schemes', () => {
        const decorations = new FindingsDecorationProvider();

        const lens = decorations.provideFileDecoration(
            mockVscode.Uri.parse('lit-critic-finding://lens/prose?active=3&total=5&maxSeverity=critical'),
        );
        assert.equal(lens.badge, '5');
        assert.equal(lens.color.id, 'charts.red');

        const count = decorations.provideFileDecoration(
            mockVscode.Uri.parse('lit-critic-count://learning-category/preferences?count=2'),
        );
        assert.equal(count.badge, '2');

        const none = decorations.provideFileDecoration(mockVscode.Uri.parse('file://x/test.txt'));
        assert.equal(none, undefined);
    });
});
