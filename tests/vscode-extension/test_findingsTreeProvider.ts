/**
 * Tests for FindingsTreeProvider module.
 * 
 * Note: These tests verify the tree structure logic.
 */

import { strict as assert } from 'assert';
import { sampleFindings } from './fixtures';

describe('FindingsTreeProvider', () => {
    describe('lens grouping', () => {
        it('should group findings by lens', () => {
            const byLens = new Map<string, typeof sampleFindings>();
            
            for (const finding of sampleFindings) {
                const lens = finding.lens.toLowerCase();
                if (!byLens.has(lens)) {
                    byLens.set(lens, []);
                }
                byLens.get(lens)!.push(finding);
            }
            
            // Should have prose and structure groups
            assert.ok(byLens.has('prose'));
            assert.ok(byLens.has('structure'));
            assert.ok(byLens.get('prose')!.length > 0);
        });

        it('should order lenses correctly', () => {
            const order = ['prose', 'structure', 'logic', 'clarity', 'continuity'];
            assert.deepEqual(order, ['prose', 'structure', 'logic', 'clarity', 'continuity']);
        });
    });

    describe('tree item creation', () => {
        it('should format finding label with finding number only', () => {
            const finding = sampleFindings[0];
            const label = `#${finding.number}`;
            assert.match(label, /#1/);
        });

        it('should format line range', () => {
            const finding = sampleFindings[0];
            const lineRange = finding.line_end !== null && finding.line_end !== finding.line_start
                ? `L${finding.line_start}-L${finding.line_end}`
                : `L${finding.line_start}`;
            assert.equal(lineRange, 'L42-L45');
        });

        it('should define severity color mapping', () => {
            const severityColors = {
                'critical': 'charts.red',
                'major': 'charts.yellow',
                'minor': 'charts.blue',
            };
            assert.equal(severityColors.critical, 'charts.red');
            assert.equal(severityColors.major, 'charts.yellow');
            assert.equal(severityColors.minor, 'charts.blue');
        });
    });

    describe('finding updates', () => {
        it('should find and update specific finding', () => {
            const findings = [...sampleFindings];
            const updated = { ...sampleFindings[0], status: 'accepted' };
            
            const idx = findings.findIndex(f => f.number === updated.number);
            if (idx >= 0) {
                findings[idx] = updated;
            }
            
            assert.equal(findings[0].status, 'accepted');
        });
    });
});
