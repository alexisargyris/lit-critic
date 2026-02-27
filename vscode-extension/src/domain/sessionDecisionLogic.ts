import * as path from 'path';

import { SessionSummary } from '../types';

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
