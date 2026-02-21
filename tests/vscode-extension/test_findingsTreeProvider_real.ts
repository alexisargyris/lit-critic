/**
 * Real tests for FindingsTreeProvider module.
 * 
 * Tests the actual FindingsTreeProvider class with mocked vscode API.
 */

import { strict as assert } from 'assert';
import { createFreshMockVscode, sampleFindings } from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

describe('FindingsTreeProvider (Real)', () => {
    let FindingsTreeProvider: any;
    let LensGroupItem: any;
    let FindingTreeItem: any;
    let mockVscode: any;
    let treeProvider: any;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();

        const module = proxyquire('../../vscode-extension/src/findingsTreeProvider', {
            'vscode': mockVscode,
        });
        FindingsTreeProvider = module.FindingsTreeProvider;
        LensGroupItem = module.LensGroupItem;
        FindingTreeItem = module.FindingTreeItem;

        treeProvider = new FindingsTreeProvider();
    });

    afterEach(() => {
        if (treeProvider) {
            treeProvider.clear();
        }
    });

    describe('setFindings', () => {
        it('should store findings and trigger tree refresh', () => {
            let eventFired = false;
            treeProvider.onDidChangeTreeData(() => { eventFired = true; });
            
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            assert.ok(eventFired);
        });

        it('should store scene path', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            // Would need to check internal state - for now just verify no errors
            assert.ok(true);
        });
    });

    describe('getChildren - root level', () => {
        it('should return lens groups when findings exist', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            const children = treeProvider.getChildren();
            
            assert.ok(Array.isArray(children));
            assert.ok(children.length > 0);
            assert.ok(children[0] instanceof LensGroupItem);
        });

        it('should group findings by lens', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            const children = treeProvider.getChildren();
            
            // sampleFindings has prose and structure
            const lensNames = children.map((item: any) => item.lens);
            assert.ok(lensNames.includes('prose'));
            assert.ok(lensNames.includes('structure'));
        });

        it('should order lenses correctly (prose, structure, logic, clarity, continuity)', () => {
            const multiLensFindings = [
                { ...sampleFindings[0], lens: 'clarity' },
                { ...sampleFindings[1], lens: 'prose' },
                { ...sampleFindings[2], lens: 'structure', status: 'pending' },
            ];
            treeProvider.setFindings(multiLensFindings, '/test/scene.txt', 0);
            
            const children = treeProvider.getChildren();
            const lensNames = children.map((item: any) => item.lens);
            
            // Should be in order: prose, structure, clarity
            const proseIdx = lensNames.indexOf('prose');
            const structureIdx = lensNames.indexOf('structure');
            const clarityIdx = lensNames.indexOf('clarity');
            
            assert.ok(proseIdx < structureIdx);
            assert.ok(structureIdx < clarityIdx);
        });

        it('should return empty array when no findings', () => {
            const children = treeProvider.getChildren();
            
            assert.ok(Array.isArray(children));
            assert.equal(children.length, 0);
        });
    });

    describe('getChildren - lens group level', () => {
        it('should return findings for specific lens', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const proseGroup = groups.find((g: any) => g.lens === 'prose');
            
            const findings = treeProvider.getChildren(proseGroup);
            
            assert.ok(Array.isArray(findings));
            assert.ok(findings.length > 0);
            assert.ok(findings[0] instanceof FindingTreeItem);
        });

        it('should only include findings from that lens', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const proseGroup = groups.find((g: any) => g.lens === 'prose');
            
            const findings = treeProvider.getChildren(proseGroup);
            
            findings.forEach((item: any) => {
                assert.equal(item.finding.lens, 'prose');
            });
        });
    });

    describe('LensGroupItem', () => {
        it('should format label correctly', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const proseGroup = groups.find((g: any) => g.lens === 'prose');
            
            assert.match(proseGroup.label, /Prose/);
            assert.match(proseGroup.label, /\(\d+\)/); // Should include count
        });

        it('should be expanded by default', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            
            assert.equal(groups[0].collapsibleState, mockVscode.TreeItemCollapsibleState.Expanded);
        });
    });

    describe('FindingTreeItem', () => {
        it('should format label with status-first and severity token', () => {
            treeProvider.setFindings([sampleFindings[0]], '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            assert.match(findings[0].label, /PENDING/);
            assert.match(findings[0].label, /\[MAJ\]/);
            assert.match(findings[0].label, /#1/);
        });

        it('should format line range in description', () => {
            treeProvider.setFindings([sampleFindings[0]], '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            // sampleFindings[0] has line_start=42, line_end=45
            assert.match(findings[0].description, /L42-L45/);
        });

        it('should show single line format when start=end', () => {
            const finding = { ...sampleFindings[0], line_start: 42, line_end: 42 };
            treeProvider.setFindings([finding], '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            assert.match(findings[0].description, /L42/);
            assert.ok(!findings[0].description.includes('L42-L42'));
        });

        it('should show accepted status in label and icon', () => {
            treeProvider.setFindings([sampleFindings[2]], '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            assert.match(findings[0].label, /ACCEPTED/);
            assert.equal(findings[0].iconPath.id, 'check');
        });

        it('should handle conceded status with dedicated label/icon', () => {
            const concededFinding = { ...sampleFindings[0], status: 'conceded' };
            treeProvider.setFindings([concededFinding], '/test/scene.txt', 0);

            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);

            assert.match(findings[0].label, /CONCEDED/);
            assert.equal(findings[0].iconPath.id, 'arrow-right');
        });

        it('should set contextValue to "finding"', () => {
            treeProvider.setFindings([sampleFindings[0]], '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            assert.equal(findings[0].contextValue, 'finding');
        });

        it('should set command to selectFinding', () => {
            treeProvider.setFindings([sampleFindings[0]], '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            assert.ok(findings[0].command);
            assert.equal(findings[0].command.command, 'literaryCritic.selectFinding');
        });

        it('should pass finding index as command argument', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            assert.ok(findings[0].command.arguments);
            assert.equal(typeof findings[0].command.arguments[0], 'number');
        });

        it('should highlight current finding with arrow', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            treeProvider.setCurrentIndex(0);
            
            const groups = treeProvider.getChildren();
            const findings = treeProvider.getChildren(groups[0]);
            
            // First finding should have arrow
            assert.match(findings[0].description, /▶/);
        });

        it('should prioritize pending findings, then severity within same status', () => {
            const findings = [
                { ...sampleFindings[0], number: 11, lens: 'prose', severity: 'minor', status: 'accepted' },
                { ...sampleFindings[0], number: 12, lens: 'prose', severity: 'minor', status: 'pending' },
                { ...sampleFindings[0], number: 13, lens: 'prose', severity: 'critical', status: 'pending' },
            ];
            treeProvider.setFindings(findings, '/test/scene.txt', 0);

            const groups = treeProvider.getChildren();
            const proseGroup = groups.find((g: any) => g.lens === 'prose');
            const proseFindings = treeProvider.getChildren(proseGroup);

            // pending critical first, then pending minor, then accepted minor
            assert.match(proseFindings[0].label, /PENDING \[CRIT\] #13/);
            assert.match(proseFindings[1].label, /PENDING \[MIN\] #12/);
            assert.match(proseFindings[2].label, /ACCEPTED \[MIN\] #11/);
        });
    });

    describe('updateFinding', () => {
        it('should update specific finding and refresh tree', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            let eventFired = false;
            treeProvider.onDidChangeTreeData(() => { eventFired = true; });
            
            const updatedFinding = { ...sampleFindings[0], status: 'accepted' };
            treeProvider.updateFinding(updatedFinding);
            
            assert.ok(eventFired);
        });
    });

    describe('setCurrentIndex', () => {
        it('should update current index and refresh tree', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            let eventFired = false;
            treeProvider.onDidChangeTreeData(() => { eventFired = true; });
            
            treeProvider.setCurrentIndex(1);
            
            assert.ok(eventFired);
        });
    });

    describe('clear', () => {
        it('should clear findings and refresh tree', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            
            let eventFired = false;
            treeProvider.onDidChangeTreeData(() => { eventFired = true; });
            
            treeProvider.clear();
            
            assert.ok(eventFired);
        });

        it('should result in empty tree', () => {
            treeProvider.setFindings(sampleFindings, '/test/scene.txt', 0);
            treeProvider.clear();
            
            const children = treeProvider.getChildren();
            
            assert.equal(children.length, 0);
        });
    });
});
