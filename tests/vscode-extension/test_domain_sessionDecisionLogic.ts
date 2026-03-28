import { strict as assert } from 'assert';

import {
    formatSessionTypeLabel,
    formatSessionLabel,
    getSessionType,
    tryParseRepoPathInvalidDetail,
} from '../../vscode-extension/src/domain/sessionDecisionLogic';

describe('domain/sessionDecisionLogic', () => {
    it('parses repo_path_invalid payload from HTTP error message', () => {
        const detail = tryParseRepoPathInvalidDetail(
            'HTTP 422: {"code":"repo_path_invalid","message":"bad path"}'
        );

        assert.deepEqual(detail, { code: 'repo_path_invalid', message: 'bad path' });
    });

    it('returns null when message is not parseable HTTP payload', () => {
        assert.equal(tryParseRepoPathInvalidDetail('plain error'), null);
    });

    it('formats session label with basename and id', () => {
        const label = formatSessionLabel({
            id: 7,
            status: 'active',
            scene_path: '/tmp/path/chapter-1.txt',
            model: 'sonnet',
            created_at: '2026-02-23T12:00:00Z',
            total_findings: 10,
            accepted_count: 1,
            rejected_count: 2,
            withdrawn_count: 0,
        });

        assert.equal(label, '#7 — chapter-1.txt');
    });

    it('derives session type from depth_mode', () => {
        assert.equal(getSessionType({ depth_mode: 'preflight' } as any), 'unknown');
        assert.equal(getSessionType({ depth_mode: 'quick' } as any), 'quick');
        assert.equal(getSessionType({ depth_mode: 'deep' } as any), 'deep');
    });

    it('falls back to unknown session type when depth_mode is missing', () => {
        assert.equal(getSessionType({} as any), 'unknown');
        assert.equal(formatSessionTypeLabel({} as any), 'Unknown');
    });
});
