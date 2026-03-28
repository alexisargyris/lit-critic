import { ApiClient } from '../apiClient';
import { KnowledgeTreeProvider } from '../knowledgeTreeProvider';
import { KnowledgeReviewViewProvider } from '../knowledgeReviewViewProvider';
import {
    KnowledgeCategoryKey,
    KnowledgeEntityTreeItemPayload,
    KnowledgeOverrideRecord,
    KnowledgeReviewPanelFieldState,
    KnowledgeReviewPanelState,
} from '../types';

// ---------------------------------------------------------------------------
// Deps interface — injected by extension.ts
// ---------------------------------------------------------------------------

export interface KnowledgeReviewHelperDeps {
    ensureKnowledgeReviewPanel: () => KnowledgeReviewViewProvider;
    knowledgeTreeProvider: KnowledgeTreeProvider;
    detectProjectPath: () => string | undefined;
    ensureServer: () => Promise<void>;
    ensureApiClient: () => ApiClient;
    showInformationMessage: (msg: string) => void;
    showErrorMessage: (msg: string) => void;
}

// ---------------------------------------------------------------------------
// Pure helpers — no external deps
// ---------------------------------------------------------------------------

export const KNOWLEDGE_FIELD_ORDER: Record<KnowledgeCategoryKey, string[]> = {
    characters: ['name', 'category'],
    terms: ['term', 'definition', 'translation', 'notes', 'category'],
    threads: ['question', 'status', 'notes', 'thread_id', 'opened_in', 'last_advanced'],
    timeline: ['summary', 'chrono_hint', 'scene_filename'],
};

export const KNOWLEDGE_SYSTEM_FIELD_ORDER = ['id', 'entity_key', 'stale', 'flagged', 'flagged_reason', 'entity_locked', 'first_seen', 'last_updated'];

export function isKnowledgeCategoryKey(value: string): value is KnowledgeCategoryKey {
    return value === 'characters' || value === 'terms' || value === 'threads' || value === 'timeline';
}

export function toOptionalString(value: unknown): string | undefined {
    if (typeof value !== 'string') {
        return undefined;
    }
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : undefined;
}

export function isKnowledgeFieldScalar(value: unknown): boolean {
    return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
}

export function knowledgeFieldValueToString(value: unknown): string {
    if (typeof value === 'string') {
        return value;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
        return String(value);
    }
    return '';
}

export function getKnowledgeEntityLabel(category: KnowledgeCategoryKey, entity: Record<string, unknown>, index: number): string {
    const fallback = `${category.slice(0, 1).toUpperCase()}${category.slice(1)} #${index + 1}`;
    if (category === 'characters') {
        return String(entity.name ?? entity.character ?? entity.entity_key ?? fallback);
    }
    if (category === 'terms') {
        return String(entity.term ?? entity.name ?? entity.entity_key ?? fallback);
    }
    if (category === 'threads') {
        return String(entity.thread_id ?? entity.title ?? entity.entity_key ?? fallback);
    }
    return String(entity.scene_filename ?? entity.summary ?? entity.entity_key ?? fallback);
}

export function getEffectiveEntityLabel(
    category: KnowledgeCategoryKey,
    extractedLabel: string,
    overrideValues?: Map<string, string>,
): string {
    if (!overrideValues) { return extractedLabel; }
    if (category === 'characters') {
        return overrideValues.get('name') ?? extractedLabel;
    }
    if (category === 'terms') {
        return overrideValues.get('term') ?? overrideValues.get('name') ?? extractedLabel;
    }
    if (category === 'threads') {
        return overrideValues.get('thread_id') ?? overrideValues.get('title') ?? extractedLabel;
    }
    // timeline
    return overrideValues.get('scene_filename') ?? overrideValues.get('summary') ?? extractedLabel;
}

export function getKnowledgeEntityKey(category: KnowledgeCategoryKey, entity: Record<string, unknown>, index: number): string {
    return toOptionalString(entity.entity_key)
        ?? (category === 'characters' ? toOptionalString(entity.name) : undefined)
        ?? (category === 'terms' ? toOptionalString(entity.term) : undefined)
        ?? (category === 'threads' ? toOptionalString(entity.thread_id) : undefined)
        ?? (category === 'timeline' ? toOptionalString(entity.scene_filename) : undefined)
        ?? `${category}:${index + 1}`;
}

export function getKnowledgeCategoryLabel(category: KnowledgeEntityTreeItemPayload['category']): string {
    switch (category) {
    case 'characters':
        return 'Characters';
    case 'terms':
        return 'Terms';
    case 'threads':
        return 'Threads';
    case 'timeline':
        return 'Timeline';
    default:
        return category;
    }
}

export function sortKnowledgeFields(fieldNames: string[], category: KnowledgeCategoryKey): string[] {
    const priority = KNOWLEDGE_FIELD_ORDER[category] ?? [];

    return [...fieldNames].sort((a, b) => {
        const aSystemIdx = KNOWLEDGE_SYSTEM_FIELD_ORDER.indexOf(a);
        const bSystemIdx = KNOWLEDGE_SYSTEM_FIELD_ORDER.indexOf(b);
        const aIsSystem = aSystemIdx >= 0;
        const bIsSystem = bSystemIdx >= 0;

        if (aIsSystem !== bIsSystem) { return aIsSystem ? 1 : -1; }
        if (aIsSystem && bIsSystem) { return aSystemIdx - bSystemIdx; }

        const aPriority = priority.indexOf(a);
        const bPriority = priority.indexOf(b);
        const aKnown = aPriority >= 0;
        const bKnown = bPriority >= 0;
        if (aKnown !== bKnown) { return aKnown ? -1 : 1; }
        if (aKnown && bKnown) { return aPriority - bPriority; }
        return 0;
    });
}

export function buildKnowledgeReviewPanelState(
    payload: KnowledgeEntityTreeItemPayload,
    options?: {
        overrideValues?: Map<string, string>;
        selectedFieldName?: string;
        status?: KnowledgeReviewPanelState['status'];
        statusMessage?: string;
        lastSavedAt?: string | null;
    },
): KnowledgeReviewPanelState {
    const fieldNames = Array.from(new Set([
        ...Object.entries(payload.entity)
            .filter(([fieldName, value]) => fieldName !== 'entity_key' && isKnowledgeFieldScalar(value))
            .map(([fieldName]) => fieldName),
        ...payload.overrideFields,
        ...Array.from(options?.overrideValues?.keys() ?? []),
    ])).filter((fieldName) => fieldName !== 'entity_key');

    const sortedFieldNames = sortKnowledgeFields(fieldNames, payload.category);
    const fields: KnowledgeReviewPanelFieldState[] = sortedFieldNames.map((fieldName) => {
        const rawSource = payload.rawEntity ?? payload.entity;
        const extractedValue = knowledgeFieldValueToString(
            rawSource[fieldName] !== undefined ? rawSource[fieldName] : payload.entity[fieldName],
        );
        const hasOverride = options?.overrideValues?.has(fieldName) ?? payload.overrideFields.includes(fieldName);
        const overrideValue = hasOverride
            ? (options?.overrideValues?.get(fieldName) ?? '')
            : null;
        const effectiveValue = overrideValue ?? extractedValue;

        const valueTruthy = effectiveValue !== ''
            && effectiveValue !== 'false'
            && effectiveValue !== '0'
            && effectiveValue !== 'null'
            && effectiveValue !== 'None';
        let stateColor: KnowledgeReviewPanelFieldState['stateColor'] = null;
        if (fieldName === 'stale' && valueTruthy) {
            stateColor = 'stale';
        } else if ((fieldName === 'flagged' || fieldName === 'flagged_reason') && valueTruthy) {
            stateColor = 'flagged';
        } else if (fieldName === 'entity_locked' && valueTruthy) {
            stateColor = 'locked';
        } else if (hasOverride) {
            stateColor = 'overridden';
        }

        return {
            fieldName,
            fieldLabel: fieldName,
            extractedValue,
            overrideValue,
            effectiveValue,
            draftValue: effectiveValue,
            hasOverride,
            isDirty: false,
            stateColor,
        };
    });

    return {
        category: payload.category,
        categoryLabel: getKnowledgeCategoryLabel(payload.category),
        entityKey: payload.entityKey,
        entityLabel: getEffectiveEntityLabel(payload.category, payload.label, options?.overrideValues),
        locked: payload.locked,
        stale: payload.stale ?? false,
        flagged: payload.flagged ?? false,
        hasOverrides: payload.hasOverrides,
        fields,
        selectedFieldName: fields.some((field) => field.fieldName === options?.selectedFieldName)
            ? options?.selectedFieldName
            : fields[0]?.fieldName,
        dirty: false,
        status: options?.status ?? 'idle',
        statusMessage: options?.statusMessage,
        lastSavedAt: options?.lastSavedAt ?? null,
    };
}

export function buildKnowledgeOverrideValueMap(
    overrides: KnowledgeOverrideRecord[] | undefined,
    entityKey: string,
): Map<string, string> {
    const map = new Map<string, string>();
    if (!Array.isArray(overrides)) {
        return map;
    }

    for (const override of overrides) {
        if (toOptionalString(override.entity_key) !== entityKey) {
            continue;
        }

        const fieldName = toOptionalString(override.field_name);
        if (!fieldName) {
            continue;
        }

        map.set(fieldName, knowledgeFieldValueToString(override.override_value ?? override.value));
    }

    return map;
}

export function buildKnowledgeEntityPayloadFromReview(
    category: KnowledgeCategoryKey,
    entityKey: string,
    review: { entities?: Array<Record<string, unknown>>; overrides?: KnowledgeOverrideRecord[] },
    entityLabel?: string,
    fallbackPayload?: KnowledgeEntityTreeItemPayload,
): KnowledgeEntityTreeItemPayload | null {
    const entities = Array.isArray(review.entities)
        ? review.entities.filter((entry): entry is Record<string, unknown> => Boolean(entry && typeof entry === 'object'))
        : [];
    const entityIndex = entities.findIndex((entity, index) => getKnowledgeEntityKey(category, entity, index) === entityKey);
    const entity = entityIndex >= 0
        ? entities[entityIndex]
        : fallbackPayload?.category === category && fallbackPayload.entityKey === entityKey
            ? fallbackPayload.entity
            : null;

    if (!entity) {
        return null;
    }

    const overrideFields = Array.isArray(review.overrides)
        ? review.overrides
            .filter((override) => toOptionalString(override.entity_key) === entityKey)
            .map((override) => toOptionalString(override.field_name))
            .filter((fieldName): fieldName is string => Boolean(fieldName))
        : (fallbackPayload?.overrideFields ?? []);

    return {
        category,
        entityKey,
        label: entityIndex >= 0
            ? getKnowledgeEntityLabel(category, entity, entityIndex)
            : (entityLabel ?? fallbackPayload?.label ?? entityKey),
        entity,
        overrideFields: Array.from(new Set(overrideFields)),
        overrideCount: Array.from(new Set(overrideFields)).length,
        hasOverrides: overrideFields.length > 0,
        locked: Boolean(entity.entity_locked),
    };
}

export function resolveKnowledgeTreeItemLabel(value: unknown): string | undefined {
    if (typeof value === 'string') {
        return toOptionalString(value);
    }

    if (value && typeof value === 'object') {
        const label = (value as { label?: unknown }).label;
        if (typeof label === 'string') {
            return toOptionalString(label);
        }
    }

    return undefined;
}

export function resolveKnowledgeEntityIdentity(item: unknown): {
    category: KnowledgeCategoryKey;
    entityKey: string;
    label: string;
} | null {
    if (!item || typeof item !== 'object') {
        return null;
    }

    const record = item as Record<string, unknown>;
    const id = toOptionalString(record.id);
    if (!id || !id.startsWith('knowledge:entity:')) {
        return null;
    }

    const identity = id.slice('knowledge:entity:'.length);
    const categorySeparator = identity.indexOf(':');
    const indexSeparator = identity.lastIndexOf(':');
    if (categorySeparator <= 0 || indexSeparator <= categorySeparator) {
        return null;
    }

    const category = identity.slice(0, categorySeparator);
    const entityKey = identity.slice(categorySeparator + 1, indexSeparator);
    if (!isKnowledgeCategoryKey(category) || entityKey.length === 0) {
        return null;
    }

    return {
        category,
        entityKey,
        label: resolveKnowledgeTreeItemLabel(record.label) ?? entityKey,
    };
}

// ---------------------------------------------------------------------------
// Helpers that require injected collaborators
// ---------------------------------------------------------------------------

export function resolveKnowledgeEntityPayload(
    item: unknown,
    deps: Pick<KnowledgeReviewHelperDeps, 'knowledgeTreeProvider'>,
): KnowledgeEntityTreeItemPayload | null {
    const candidates = [
        (item as { payload?: unknown } | undefined)?.payload,
        (item as { command?: { arguments?: unknown[] } } | undefined)?.command?.arguments?.[0],
        item,
    ];

    for (const candidate of candidates) {
        if (!candidate || typeof candidate !== 'object') {
            continue;
        }

        const record = candidate as Record<string, unknown>;
        if (
            typeof record.category !== 'string'
            || typeof record.entityKey !== 'string'
            || typeof record.label !== 'string'
            || typeof record.entity !== 'object'
            || !record.entity
            || !Array.isArray(record.overrideFields)
        ) {
            continue;
        }

        return record as unknown as KnowledgeEntityTreeItemPayload;
    }

    const identity = resolveKnowledgeEntityIdentity(item);
    return identity ? deps.knowledgeTreeProvider.getEntityPayload(identity.category, identity.entityKey) : null;
}

export function resolveKnowledgeEntityReviewTarget(
    item: unknown,
    deps: Pick<KnowledgeReviewHelperDeps, 'knowledgeTreeProvider'>,
): {
    category: KnowledgeCategoryKey;
    entityKey: string;
    label: string;
    payload?: KnowledgeEntityTreeItemPayload;
} | null {
    const payload = resolveKnowledgeEntityPayload(item, deps);
    if (payload) {
        return {
            category: payload.category,
            entityKey: payload.entityKey,
            label: payload.label,
            payload,
        };
    }

    return resolveKnowledgeEntityIdentity(item);
}

export async function loadKnowledgeEntityPayload(
    category: KnowledgeCategoryKey,
    entityKey: string,
    entityLabel: string | undefined,
    fallbackPayload: KnowledgeEntityTreeItemPayload | undefined,
    deps: Pick<KnowledgeReviewHelperDeps, 'knowledgeTreeProvider' | 'detectProjectPath' | 'ensureServer' | 'ensureApiClient'>,
): Promise<KnowledgeEntityTreeItemPayload | null> {
    const cachedPayload = deps.knowledgeTreeProvider.getEntityPayload(category, entityKey);
    if (cachedPayload) {
        return cachedPayload;
    }

    const projectPath = deps.detectProjectPath();
    if (!projectPath) {
        return fallbackPayload ?? null;
    }

    await deps.ensureServer();
    const review = await deps.ensureApiClient().getKnowledgeReview(category, projectPath);
    return buildKnowledgeEntityPayloadFromReview(category, entityKey, review, entityLabel, fallbackPayload);
}

export async function hydrateKnowledgeReviewPanel(
    category: KnowledgeCategoryKey,
    entityKey: string,
    entityLabel: string,
    fallbackPayload: KnowledgeEntityTreeItemPayload | undefined,
    options: {
        status?: KnowledgeReviewPanelState['status'];
        statusMessage?: string;
        lastSavedAt?: string | null;
    } | undefined,
    deps: KnowledgeReviewHelperDeps,
): Promise<KnowledgeReviewPanelState | null> {
    const panel = deps.ensureKnowledgeReviewPanel();
    const previousState = panel.getState();

    try {
        const payload = await loadKnowledgeEntityPayload(category, entityKey, entityLabel, fallbackPayload, deps);
        if (!payload) {
            throw new Error(`Could not load ${entityLabel} from knowledge review data.`);
        }

        const projectPath = deps.detectProjectPath();
        if (!projectPath) {
            throw new Error('Could not detect project directory (no CANON.md found in workspace).');
        }

        await deps.ensureServer();
        const review = await deps.ensureApiClient().getKnowledgeReview(category, projectPath);
        const overrideValues = buildKnowledgeOverrideValueMap(review.overrides, entityKey);

        const rawEntities = Array.isArray(review.raw_entities) ? review.raw_entities : [];
        const rawEntityIndex = rawEntities.findIndex(
            (e: Record<string, unknown>, i: number) => getKnowledgeEntityKey(category, e, i) === entityKey,
        );
        const enrichedPayload: KnowledgeEntityTreeItemPayload = rawEntityIndex >= 0
            ? { ...payload, rawEntity: rawEntities[rawEntityIndex] }
            : payload;

        const nextState = buildKnowledgeReviewPanelState(enrichedPayload, {
            overrideValues,
            selectedFieldName: previousState?.category === category && previousState?.entityKey === entityKey
                ? previousState.selectedFieldName
                : undefined,
            status: options?.status ?? 'idle',
            statusMessage: options?.statusMessage,
            lastSavedAt: options?.lastSavedAt ?? previousState?.lastSavedAt ?? null,
        });
        panel.updateState(nextState);
        return nextState;
    } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        const payload = fallbackPayload
            ?? ((previousState && previousState.category === category && previousState.entityKey === entityKey)
                ? (deps.knowledgeTreeProvider.getEntityPayload(category, entityKey) ?? undefined)
                : undefined);

        if (payload) {
            panel.updateState(buildKnowledgeReviewPanelState(payload, {
                selectedFieldName: previousState?.selectedFieldName,
                lastSavedAt: previousState?.lastSavedAt ?? null,
            }));
        }

        deps.showErrorMessage(`lit-critic: ${detail}`);
        return null;
    }
}

export async function navigateKnowledgeReviewPanel(
    direction: 'next' | 'previous',
    deps: KnowledgeReviewHelperDeps,
): Promise<void> {
    const panel = deps.ensureKnowledgeReviewPanel();
    const currentState = panel.getState();
    if (!currentState) {
        deps.showInformationMessage('lit-critic: Knowledge review panel is not open.');
        return;
    }

    const adjacentPayload = deps.knowledgeTreeProvider.getAdjacentEntityPayload(
        currentState.category,
        currentState.entityKey,
        direction,
    );
    if (!adjacentPayload) {
        deps.showInformationMessage(`lit-critic: No ${direction} knowledge entry available.`);
        return;
    }

    panel.show(buildKnowledgeReviewPanelState(adjacentPayload, {}));
    await hydrateKnowledgeReviewPanel(
        adjacentPayload.category,
        adjacentPayload.entityKey,
        adjacentPayload.label,
        adjacentPayload,
        undefined,
        deps,
    );
}
