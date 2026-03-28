import * as path from 'path';

import { SessionSummary } from '../types';

export type SessionType = 'quick' | 'deep' | 'unknown';

export function tryParseRepoPathInvalidDetail(message: string): { code?: string; message?: string } | null {
    const match = message.match(/^HTTP\s+\d+:\s+(\{.*\})$/);
    if (!match) {
        return null;
    }

    try {
        const detail = JSON.parse(match[1]) as { code?: string; message?: string };
        if (detail && detail.code === 'repo_path_invalid') {
            return detail;
        }
    } catch {
        // ignore parse failures
    }

    return null;
}

export function formatSessionLabel(session: SessionSummary): string {
    return `#${session.id} — ${path.basename(session.scene_path)}`;
}

export function getSessionType(session: Pick<SessionSummary, 'depth_mode'>): SessionType {
    const mode = String(session.depth_mode ?? '').trim().toLowerCase();
    if (mode === 'quick' || mode === 'deep') {
        return mode;
    }
    return 'unknown';
}

export function formatSessionTypeLabel(session: Pick<SessionSummary, 'depth_mode'>): string {
    const sessionType = getSessionType(session);
    if (sessionType === 'quick') {
        return 'Quick';
    }
    if (sessionType === 'deep') {
        return 'Deep';
    }
    return 'Unknown';
}
