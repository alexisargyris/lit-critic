import { InputStalenessEntry } from '../types';

export { InputStalenessEntry };

// ---------------------------------------------------------------------------
// StalenessRegistry — tracks which inputs/knowledge/sessions are stale
// ---------------------------------------------------------------------------

export class StalenessRegistry {
    private _entries: Map<string, InputStalenessEntry> = new Map();

    update(entries: InputStalenessEntry[]): void {
        this._entries.clear();
        for (const entry of entries) {
            this._entries.set(entry.path, entry);
        }
    }

    clear(): void {
        this._entries.clear();
    }

    isInputStale(path: string): boolean {
        return this._entries.has(path);
    }

    isKnowledgeEntryStale(category: string, entityKey: string): boolean {
        for (const entry of this._entries.values()) {
            const affected = entry.affected_knowledge;
            if (affected === 'all') {
                return true;
            }
            if (affected.some(k => k.category === category && k.entity_key === entityKey)) {
                return true;
            }
        }
        return false;
    }

    isSessionStale(sessionId: number): boolean {
        for (const entry of this._entries.values()) {
            if (entry.affected_sessions.includes(sessionId)) {
                return true;
            }
        }
        return false;
    }

    getStaleInputForSession(sessionId: number): string | undefined {
        for (const entry of this._entries.values()) {
            if (entry.affected_sessions.includes(sessionId)) {
                return entry.path;
            }
        }
        return undefined;
    }
}
