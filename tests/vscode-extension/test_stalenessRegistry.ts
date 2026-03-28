import { strict as assert } from 'assert';

import { StalenessRegistry } from '../../vscode-extension/src/workflows/stalenessRegistry';
import { InputStalenessEntry } from '../../vscode-extension/src/workflows/stalenessRegistry';

function makeEntry(overrides: Partial<InputStalenessEntry> = {}): InputStalenessEntry {
    return {
        path: '/project/scene1.txt',
        type: 'scene',
        affected_knowledge: [],
        affected_sessions: [],
        ...overrides,
    };
}

describe('StalenessRegistry', () => {
    let registry: StalenessRegistry;

    beforeEach(() => {
        registry = new StalenessRegistry();
    });

    describe('update() and isInputStale()', () => {
        it('returns false for unknown path before any update', () => {
            assert.equal(registry.isInputStale('/some/path.txt'), false);
        });

        it('returns true for a path present in the update', () => {
            registry.update([makeEntry({ path: '/project/ch1.txt' })]);
            assert.equal(registry.isInputStale('/project/ch1.txt'), true);
        });

        it('returns false for a path not in the update', () => {
            registry.update([makeEntry({ path: '/project/ch1.txt' })]);
            assert.equal(registry.isInputStale('/project/ch2.txt'), false);
        });

        it('replaces previous entries on each update call', () => {
            registry.update([makeEntry({ path: '/old.txt' })]);
            registry.update([makeEntry({ path: '/new.txt' })]);
            assert.equal(registry.isInputStale('/old.txt'), false);
            assert.equal(registry.isInputStale('/new.txt'), true);
        });

        it('handles empty update (clears all entries)', () => {
            registry.update([makeEntry({ path: '/something.txt' })]);
            registry.update([]);
            assert.equal(registry.isInputStale('/something.txt'), false);
        });
    });

    describe('clear()', () => {
        it('removes all entries so isInputStale returns false', () => {
            registry.update([makeEntry({ path: '/a.txt' }), makeEntry({ path: '/b.txt' })]);
            registry.clear();
            assert.equal(registry.isInputStale('/a.txt'), false);
            assert.equal(registry.isInputStale('/b.txt'), false);
        });
    });

    describe('isKnowledgeEntryStale()', () => {
        it('returns false when no entries', () => {
            assert.equal(registry.isKnowledgeEntryStale('characters', 'Alice'), false);
        });

        it('returns true when affected_knowledge is "all"', () => {
            registry.update([makeEntry({ affected_knowledge: 'all' })]);
            assert.equal(registry.isKnowledgeEntryStale('characters', 'Alice'), true);
            assert.equal(registry.isKnowledgeEntryStale('terms', 'magic'), true);
        });

        it('returns true when the category+entityKey is in the affected list', () => {
            registry.update([
                makeEntry({
                    affected_knowledge: [
                        { category: 'characters', entity_key: 'Alice' },
                        { category: 'terms', entity_key: 'sword' },
                    ],
                }),
            ]);
            assert.equal(registry.isKnowledgeEntryStale('characters', 'Alice'), true);
            assert.equal(registry.isKnowledgeEntryStale('terms', 'sword'), true);
        });

        it('returns false when different entity in same category', () => {
            registry.update([
                makeEntry({
                    affected_knowledge: [{ category: 'characters', entity_key: 'Bob' }],
                }),
            ]);
            assert.equal(registry.isKnowledgeEntryStale('characters', 'Alice'), false);
        });

        it('returns false when same entity key in different category', () => {
            registry.update([
                makeEntry({
                    affected_knowledge: [{ category: 'terms', entity_key: 'Alice' }],
                }),
            ]);
            assert.equal(registry.isKnowledgeEntryStale('characters', 'Alice'), false);
        });

        it('returns true if any entry matches even when others do not', () => {
            registry.update([
                makeEntry({ path: '/a.txt', affected_knowledge: [] }),
                makeEntry({
                    path: '/b.txt',
                    affected_knowledge: [{ category: 'characters', entity_key: 'Alice' }],
                }),
            ]);
            assert.equal(registry.isKnowledgeEntryStale('characters', 'Alice'), true);
        });
    });

    describe('isSessionStale()', () => {
        it('returns false when no entries', () => {
            assert.equal(registry.isSessionStale(42), false);
        });

        it('returns true when session id is in affected_sessions', () => {
            registry.update([makeEntry({ affected_sessions: [1, 2, 42] })]);
            assert.equal(registry.isSessionStale(42), true);
        });

        it('returns false when session id is not in affected_sessions', () => {
            registry.update([makeEntry({ affected_sessions: [1, 2] })]);
            assert.equal(registry.isSessionStale(42), false);
        });
    });

    describe('getStaleInputForSession()', () => {
        it('returns undefined when no entries', () => {
            assert.equal(registry.getStaleInputForSession(1), undefined);
        });

        it('returns the path of the entry that has the session id', () => {
            registry.update([
                makeEntry({ path: '/ch1.txt', affected_sessions: [10] }),
                makeEntry({ path: '/ch2.txt', affected_sessions: [20] }),
            ]);
            assert.equal(registry.getStaleInputForSession(10), '/ch1.txt');
            assert.equal(registry.getStaleInputForSession(20), '/ch2.txt');
        });

        it('returns undefined when session id is not in any entry', () => {
            registry.update([makeEntry({ path: '/ch1.txt', affected_sessions: [10] })]);
            assert.equal(registry.getStaleInputForSession(99), undefined);
        });
    });
});
