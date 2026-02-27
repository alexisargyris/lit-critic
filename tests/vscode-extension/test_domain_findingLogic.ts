import { strict as assert } from 'assert';

import {
    cloneDiscussionTurns,
    getLatestFindingStatus,
    getSafeTotalFindings,
    hasFindingContextChanged,
    isTerminalFindingStatus,
    resolveFallbackFinding,
    resolvePresentedFindingIndex,
} from '../../vscode-extension/src/domain/findingLogic';
import { Finding, FindingResponse } from '../../vscode-extension/src/types';

function makeFinding(overrides: Partial<Finding> = {}): Finding {
    return {
        number: 1,
        severity: 'major',
        lens: 'prose',
        location: 'Paragraph 1',
        line_start: 10,
        line_end: 12,
        scene_path: '/tmp/scene.txt',
        evidence: 'evidence',
        impact: 'impact',
        options: [],
        flagged_by: [],
        ambiguity_type: null,
        stale: false,
        status: 'pending',
        ...overrides,
    };
}

describe('domain/findingLogic', () => {
    it('clones discussion turns without mutating source references', () => {
        const source = [{ role: 'user', content: 'hello' }];
        const cloned = cloneDiscussionTurns(source);

        assert.deepEqual(cloned, source);
        assert.notEqual(cloned[0], source[0]);
    });

    it('detects finding context changes on tracked fields', () => {
        const previous = makeFinding();
        const next = makeFinding({ evidence: 'changed evidence' });

        assert.equal(hasFindingContextChanged(previous, next), true);
        assert.equal(hasFindingContextChanged(previous, makeFinding()), false);
    });

    it('detects terminal statuses', () => {
        assert.equal(isTerminalFindingStatus('accepted'), true);
        assert.equal(isTerminalFindingStatus('rejected'), true);
        assert.equal(isTerminalFindingStatus('withdrawn'), true);
        assert.equal(isTerminalFindingStatus('pending'), false);
    });

    it('resolves latest finding status from finding payload first', () => {
        const result = {
            response: 'ok',
            status: 'ok',
            finding_status: 'pending',
            finding: makeFinding({ status: 'accepted' }),
        };

        assert.equal(getLatestFindingStatus(result), 'accepted');
    });

    it('falls back total findings to cached findings length when needed', () => {
        const findings = [makeFinding(), makeFinding({ number: 2 })];
        assert.equal(getSafeTotalFindings(3, findings), 3);
        assert.equal(getSafeTotalFindings(0, findings), 2);
    });

    it('resolves fallback finding by preferred index, then current, then last', () => {
        const findings = [
            makeFinding({ number: 1 }),
            makeFinding({ number: 2 }),
            makeFinding({ number: 3 }),
        ];

        const preferred = resolveFallbackFinding(findings, 1, 2);
        assert.equal(preferred?.finding.number, 3);

        const current = resolveFallbackFinding(findings, 1, 99);
        assert.equal(current?.finding.number, 2);

        const last = resolveFallbackFinding(findings, 99, 99);
        assert.equal(last?.finding.number, 3);
    });

    it('resolves presented index by finding number match before response index', () => {
        const allFindings = [
            makeFinding({ number: 11 }),
            makeFinding({ number: 12 }),
            makeFinding({ number: 13 }),
        ];
        const resp: FindingResponse = {
            complete: false,
            finding: makeFinding({ number: 12 }),
            index: 0,
        };

        const resolved = resolvePresentedFindingIndex(resp, allFindings, 2, 1);
        assert.equal(resolved, 1);
    });

    it('clamps presented index into valid bounds', () => {
        const allFindings = [makeFinding({ number: 1 }), makeFinding({ number: 2 })];
        const resp: FindingResponse = { complete: false, index: 99 };

        const resolved = resolvePresentedFindingIndex(resp, allFindings, 0);
        assert.equal(resolved, 1);
    });
});
