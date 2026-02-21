import { strict as assert } from 'assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { REPO_MARKER, validateRepoPath } from '../../vscode-extension/src/repoPreflight';

describe('repoPreflight', () => {
    it('returns empty for blank path', () => {
        const result = validateRepoPath('');
        assert.equal(result.ok, false);
        assert.equal(result.reason_code, 'empty');
    });

    it('returns not_found for missing directory', () => {
        const result = validateRepoPath(path.join(os.tmpdir(), 'missing-repo-path-xyz'));
        assert.equal(result.ok, false);
        assert.equal(result.reason_code, 'not_found');
    });

    it('returns missing_marker when marker is absent', () => {
        const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-preflight-'));
        try {
            const result = validateRepoPath(tempDir);
            assert.equal(result.ok, false);
            assert.equal(result.reason_code, 'missing_marker');
        } finally {
            fs.rmSync(tempDir, { recursive: true, force: true });
        }
    });

    it('returns ok when marker exists', () => {
        const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-preflight-'));
        try {
            fs.writeFileSync(path.join(tempDir, REPO_MARKER), 'ok', 'utf8');
            const result = validateRepoPath(tempDir);
            assert.equal(result.ok, true);
            assert.equal(result.reason_code, '');
            assert.ok(result.path);
        } finally {
            fs.rmSync(tempDir, { recursive: true, force: true });
        }
    });
});
