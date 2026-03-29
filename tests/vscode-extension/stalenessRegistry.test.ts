/**
 * Tests for StalenessRegistry — hasStaleInputs() and staleInputCount()
 */

import { strict as assert } from 'assert';
import { StalenessRegistry, InputStalenessEntry } from '../../vscode-extension/src/workflows/stalenessRegistry';

function makeEntry(path: string): InputStalenessEntry {
    return {
        path,
        type: 'scene',
        affected_knowledge: [],
        affected_sessions: [],
    };
}

describe('StalenessRegistry — hasStaleInputs()', () => {
    it('returns false on an empty registry', () => {
        const registry = new StalenessRegistry();
        assert.equal(registry.hasStaleInputs(), false);
    });

    it('returns true after update() with one entry', () => {
        const registry = new StalenessRegistry();
        registry.update([makeEntry('/project/scene1.txt')]);
        assert.equal(registry.hasStaleInputs(), true);
    });

    it('returns true after update() with multiple entries', () => {
        const registry = new StalenessRegistry();
        registry.update([
            makeEntry('/project/scene1.txt'),
            makeEntry('/project/scene2.txt'),
        ]);
        assert.equal(registry.hasStaleInputs(), true);
    });

    it('returns false after clear()', () => {
        const registry = new StalenessRegistry();
        registry.update([makeEntry('/project/scene1.txt')]);
        registry.clear();
        assert.equal(registry.hasStaleInputs(), false);
    });

    it('returns false after update() with empty array', () => {
        const registry = new StalenessRegistry();
        registry.update([makeEntry('/project/scene1.txt')]);
        registry.update([]);
        assert.equal(registry.hasStaleInputs(), false);
    });
});

describe('StalenessRegistry — staleInputCount()', () => {
    it('returns 0 on an empty registry', () => {
        const registry = new StalenessRegistry();
        assert.equal(registry.staleInputCount(), 0);
    });

    it('returns 1 after update() with one entry', () => {
        const registry = new StalenessRegistry();
        registry.update([makeEntry('/project/scene1.txt')]);
        assert.equal(registry.staleInputCount(), 1);
    });

    it('returns N after update() with N entries', () => {
        const registry = new StalenessRegistry();
        registry.update([
            makeEntry('/project/scene1.txt'),
            makeEntry('/project/scene2.txt'),
            makeEntry('/project/scene3.txt'),
        ]);
        assert.equal(registry.staleInputCount(), 3);
    });

    it('returns 0 after clear()', () => {
        const registry = new StalenessRegistry();
        registry.update([makeEntry('/project/scene1.txt'), makeEntry('/project/scene2.txt')]);
        registry.clear();
        assert.equal(registry.staleInputCount(), 0);
    });

    it('deduplicates entries with the same path', () => {
        const registry = new StalenessRegistry();
        registry.update([
            makeEntry('/project/scene1.txt'),
            makeEntry('/project/scene1.txt'),
        ]);
        assert.equal(registry.staleInputCount(), 1);
    });
});
