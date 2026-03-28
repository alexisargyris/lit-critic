import { strict as assert } from 'assert';

import {
    sortKnowledgeFields,
    buildKnowledgeReviewPanelState,
    buildKnowledgeOverrideValueMap,
    isKnowledgeFieldScalar,
    knowledgeFieldValueToString,
    getKnowledgeEntityLabel,
    getKnowledgeEntityKey,
    getEffectiveEntityLabel,
    resolveKnowledgeEntityIdentity,
} from '../../vscode-extension/src/ui/knowledgeReviewHelpers';
import { KnowledgeEntityTreeItemPayload } from '../../vscode-extension/src/types';

// ---------------------------------------------------------------------------
// isKnowledgeFieldScalar
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — isKnowledgeFieldScalar()', () => {
    it('returns true for string, number, boolean', () => {
        assert.equal(isKnowledgeFieldScalar('hello'), true);
        assert.equal(isKnowledgeFieldScalar(42), true);
        assert.equal(isKnowledgeFieldScalar(false), true);
    });

    it('returns false for null, undefined, array, object', () => {
        assert.equal(isKnowledgeFieldScalar(null), false);
        assert.equal(isKnowledgeFieldScalar(undefined), false);
        assert.equal(isKnowledgeFieldScalar([]), false);
        assert.equal(isKnowledgeFieldScalar({}), false);
    });
});

// ---------------------------------------------------------------------------
// knowledgeFieldValueToString
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — knowledgeFieldValueToString()', () => {
    it('returns string as-is', () => {
        assert.equal(knowledgeFieldValueToString('Alice'), 'Alice');
        assert.equal(knowledgeFieldValueToString(''), '');
    });

    it('converts number and boolean to string', () => {
        assert.equal(knowledgeFieldValueToString(42), '42');
        assert.equal(knowledgeFieldValueToString(true), 'true');
        assert.equal(knowledgeFieldValueToString(false), 'false');
    });

    it('returns empty string for other types', () => {
        assert.equal(knowledgeFieldValueToString(null), '');
        assert.equal(knowledgeFieldValueToString(undefined), '');
        assert.equal(knowledgeFieldValueToString([]), '');
        assert.equal(knowledgeFieldValueToString({}), '');
    });
});

// ---------------------------------------------------------------------------
// getKnowledgeEntityLabel
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — getKnowledgeEntityLabel()', () => {
    it('uses name for characters', () => {
        assert.equal(getKnowledgeEntityLabel('characters', { name: 'Alice' }, 0), 'Alice');
    });

    it('falls back to entity_key for characters when name is missing', () => {
        assert.equal(getKnowledgeEntityLabel('characters', { entity_key: 'char:alice' }, 0), 'char:alice');
    });

    it('uses term for terms', () => {
        assert.equal(getKnowledgeEntityLabel('terms', { term: 'magic sword' }, 0), 'magic sword');
    });

    it('uses thread_id for threads', () => {
        assert.equal(getKnowledgeEntityLabel('threads', { thread_id: 'T-001' }, 0), 'T-001');
    });

    it('uses scene_filename for timeline', () => {
        assert.equal(getKnowledgeEntityLabel('timeline', { scene_filename: 'ch01.txt' }, 0), 'ch01.txt');
    });

    it('uses index-based fallback when all fields are missing', () => {
        assert.equal(getKnowledgeEntityLabel('characters', {}, 2), 'Characters #3');
    });
});

// ---------------------------------------------------------------------------
// getKnowledgeEntityKey
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — getKnowledgeEntityKey()', () => {
    it('prefers entity_key over all others', () => {
        assert.equal(getKnowledgeEntityKey('characters', { entity_key: 'ek:alice', name: 'Alice' }, 0), 'ek:alice');
    });

    it('falls back to name for characters', () => {
        assert.equal(getKnowledgeEntityKey('characters', { name: 'Alice' }, 0), 'Alice');
    });

    it('falls back to term for terms', () => {
        assert.equal(getKnowledgeEntityKey('terms', { term: 'sword' }, 0), 'sword');
    });

    it('falls back to thread_id for threads', () => {
        assert.equal(getKnowledgeEntityKey('threads', { thread_id: 'T-001' }, 0), 'T-001');
    });

    it('falls back to scene_filename for timeline', () => {
        assert.equal(getKnowledgeEntityKey('timeline', { scene_filename: 'ch01.txt' }, 0), 'ch01.txt');
    });

    it('uses index-based fallback when all else is missing', () => {
        assert.equal(getKnowledgeEntityKey('characters', {}, 3), 'characters:4');
    });
});

// ---------------------------------------------------------------------------
// getEffectiveEntityLabel
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — getEffectiveEntityLabel()', () => {
    it('returns extractedLabel when no overrides', () => {
        assert.equal(getEffectiveEntityLabel('characters', 'Alice'), 'Alice');
    });

    it('applies name override for characters', () => {
        const overrides = new Map([['name', 'Alicia']]);
        assert.equal(getEffectiveEntityLabel('characters', 'Alice', overrides), 'Alicia');
    });

    it('falls back to extractedLabel if override does not have the key', () => {
        const overrides = new Map([['category', 'protagonist']]);
        assert.equal(getEffectiveEntityLabel('characters', 'Alice', overrides), 'Alice');
    });

    it('applies term override for terms', () => {
        const overrides = new Map([['term', 'enchanted blade']]);
        assert.equal(getEffectiveEntityLabel('terms', 'magic sword', overrides), 'enchanted blade');
    });

    it('applies thread_id override for threads', () => {
        const overrides = new Map([['thread_id', 'T-002']]);
        assert.equal(getEffectiveEntityLabel('threads', 'T-001', overrides), 'T-002');
    });

    it('applies scene_filename override for timeline', () => {
        const overrides = new Map([['scene_filename', 'ch02.txt']]);
        assert.equal(getEffectiveEntityLabel('timeline', 'ch01.txt', overrides), 'ch02.txt');
    });
});

// ---------------------------------------------------------------------------
// sortKnowledgeFields
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — sortKnowledgeFields()', () => {
    it('puts priority fields first for characters', () => {
        const result = sortKnowledgeFields(['stale', 'name', 'category', 'custom_field'], 'characters');
        assert.equal(result[0], 'name');
        assert.equal(result[1], 'category');
        assert.ok(result.indexOf('custom_field') < result.indexOf('stale'));
        assert.equal(result[result.length - 1], 'stale');
    });

    it('puts system fields (stale, flagged, entity_locked) last', () => {
        const result = sortKnowledgeFields(['stale', 'term', 'definition', 'entity_locked'], 'terms');
        const staleIdx = result.indexOf('stale');
        const termIdx = result.indexOf('term');
        assert.ok(termIdx < staleIdx);
        assert.ok(result.indexOf('entity_locked') > result.indexOf('definition'));
    });

    it('system fields appear in KNOWLEDGE_SYSTEM_FIELD_ORDER order', () => {
        const result = sortKnowledgeFields(['last_updated', 'stale', 'first_seen'], 'characters');
        const staleIdx = result.indexOf('stale');
        const firstSeenIdx = result.indexOf('first_seen');
        const lastUpdatedIdx = result.indexOf('last_updated');
        assert.ok(staleIdx < firstSeenIdx);
        assert.ok(firstSeenIdx < lastUpdatedIdx);
    });
});

// ---------------------------------------------------------------------------
// buildKnowledgeOverrideValueMap
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — buildKnowledgeOverrideValueMap()', () => {
    it('returns empty map for undefined overrides', () => {
        const map = buildKnowledgeOverrideValueMap(undefined, 'alice');
        assert.equal(map.size, 0);
    });

    it('returns empty map when no overrides match entityKey', () => {
        const overrides = [{ entity_key: 'bob', field_name: 'name', override_value: 'Bobby' }];
        const map = buildKnowledgeOverrideValueMap(overrides, 'alice');
        assert.equal(map.size, 0);
    });

    it('returns matching overrides for entityKey', () => {
        const overrides = [
            { entity_key: 'alice', field_name: 'name', override_value: 'Alicia' },
            { entity_key: 'alice', field_name: 'category', override_value: 'hero' },
            { entity_key: 'bob', field_name: 'name', override_value: 'Bobby' },
        ];
        const map = buildKnowledgeOverrideValueMap(overrides, 'alice');
        assert.equal(map.size, 2);
        assert.equal(map.get('name'), 'Alicia');
        assert.equal(map.get('category'), 'hero');
    });

    it('falls back to override.value when override_value is absent', () => {
        const overrides = [{ entity_key: 'alice', field_name: 'name', value: 'Alicia-fallback' }];
        const map = buildKnowledgeOverrideValueMap(overrides as any, 'alice');
        assert.equal(map.get('name'), 'Alicia-fallback');
    });
});

// ---------------------------------------------------------------------------
// resolveKnowledgeEntityIdentity
// ---------------------------------------------------------------------------

describe('knowledgeReviewHelpers — resolveKnowledgeEntityIdentity()', () => {
    it('returns null for non-object input', () => {
        assert.equal(resolveKnowledgeEntityIdentity(null), null);
        assert.equal(resolveKnowledgeEntityIdentity('string'), null);
        assert.equal(resolveKnowledgeEntityIdentity(42), null);
    });

    it('returns null when id does not start with knowledge:entity:', () => {
        assert.equal(resolveKnowledgeEntityIdentity({ id: 'session:1' }), null);
        assert.equal(resolveKnowledgeEntityIdentity({ id: '' }), null);
        assert.equal(resolveKnowledgeEntityIdentity({}), null);
    });

    it('returns null for malformed identity (no index separator)', () => {
        assert.equal(resolveKnowledgeEntityIdentity({ id: 'knowledge:entity:characters:Alice' }), null);
    });

    it('parses a valid knowledge:entity: id', () => {
        const result = resolveKnowledgeEntityIdentity({
            id: 'knowledge:entity:characters:Alice:0',
        });
        assert.ok(result);
        assert.equal(result!.category, 'characters');
        assert.equal(result!.entityKey, 'Alice');
    });

    it('uses label from tree item when present', () => {
        const result = resolveKnowledgeEntityIdentity({
            id: 'knowledge:entity:terms:sword:0',
            label: 'Magic Sword',
        });
        assert.equal(result!.label, 'Magic Sword');
    });

    it('falls back to entityKey as label when label is missing', () => {
        const result = resolveKnowledgeEntityIdentity({
            id: 'knowledge:entity:terms:sword:0',
        });
        assert.equal(result!.label, 'sword');
    });
});

// ---------------------------------------------------------------------------
// buildKnowledgeReviewPanelState (focused tests)
// ---------------------------------------------------------------------------

function makePayload(overrides: Partial<KnowledgeEntityTreeItemPayload> = {}): KnowledgeEntityTreeItemPayload {
    return {
        category: 'characters',
        entityKey: 'alice',
        label: 'Alice',
        entity: { name: 'Alice', category: 'protagonist' },
        overrideFields: [],
        overrideCount: 0,
        hasOverrides: false,
        locked: false,
        ...overrides,
    };
}

describe('knowledgeReviewHelpers — buildKnowledgeReviewPanelState()', () => {
    it('includes scalar fields from entity', () => {
        const state = buildKnowledgeReviewPanelState(makePayload());
        const fieldNames = state.fields.map(f => f.fieldName);
        assert.ok(fieldNames.includes('name'));
        assert.ok(fieldNames.includes('category'));
    });

    it('excludes entity_key from fields', () => {
        const payload = makePayload({ entity: { entity_key: 'alice', name: 'Alice' } });
        const state = buildKnowledgeReviewPanelState(payload);
        const fieldNames = state.fields.map(f => f.fieldName);
        assert.ok(!fieldNames.includes('entity_key'));
    });

    it('marks hasOverride correctly when overrideValues is provided', () => {
        const state = buildKnowledgeReviewPanelState(makePayload(), {
            overrideValues: new Map([['name', 'Alicia']]),
        });
        const nameField = state.fields.find(f => f.fieldName === 'name')!;
        assert.equal(nameField.hasOverride, true);
        assert.equal(nameField.overrideValue, 'Alicia');
        assert.equal(nameField.effectiveValue, 'Alicia');
    });

    it('sets stateColor=stale when field is stale and truthy', () => {
        const payload = makePayload({ entity: { name: 'Alice', stale: true } });
        const state = buildKnowledgeReviewPanelState(payload);
        const staleField = state.fields.find(f => f.fieldName === 'stale')!;
        assert.equal(staleField.stateColor, 'stale');
    });

    it('sets stateColor=overridden when field has override', () => {
        const state = buildKnowledgeReviewPanelState(makePayload(), {
            overrideValues: new Map([['name', 'Alicia']]),
        });
        const nameField = state.fields.find(f => f.fieldName === 'name')!;
        assert.equal(nameField.stateColor, 'overridden');
    });

    it('uses extractedLabel from entity label when no override', () => {
        const state = buildKnowledgeReviewPanelState(makePayload());
        assert.equal(state.entityLabel, 'Alice');
    });

    it('reflects effective entity label from override map', () => {
        const state = buildKnowledgeReviewPanelState(makePayload(), {
            overrideValues: new Map([['name', 'Alicia']]),
        });
        assert.equal(state.entityLabel, 'Alicia');
    });

    it('applies custom status to the panel state', () => {
        const state = buildKnowledgeReviewPanelState(makePayload(), { status: 'saving' });
        assert.equal(state.status, 'saving');
    });
});
