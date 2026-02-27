import { DiscussResponse, Finding, FindingResponse } from '../types';

export interface DiscussionTurn {
    role: string;
    content: string;
}

export function cloneDiscussionTurns(turns?: DiscussionTurn[]): DiscussionTurn[] {
    return (turns || []).map((t) => ({ role: t.role, content: t.content }));
}

export function hasFindingContextChanged(previous: Finding, next: Finding): boolean {
    return (
        previous.evidence !== next.evidence
        || previous.location !== next.location
        || previous.line_start !== next.line_start
        || previous.line_end !== next.line_end
        || previous.severity !== next.severity
        || previous.impact !== next.impact
    );
}

export function isTerminalFindingStatus(status?: string): boolean {
    return status === 'accepted' || status === 'rejected' || status === 'withdrawn';
}

export function getLatestFindingStatus(result: DiscussResponse): string | undefined {
    return result.finding?.status || result.finding_status;
}

export function getSafeTotalFindings(totalFindings: number, allFindings: Finding[]): number {
    return totalFindings > 0 ? totalFindings : allFindings.length;
}

export function resolveFallbackFinding(
    allFindings: Finding[],
    currentFindingIndex: number,
    preferredIndex?: number,
): { finding: Finding; index: number } | null {
    if (allFindings.length === 0) {
        return null;
    }

    const candidates = [
        preferredIndex,
        currentFindingIndex,
        allFindings.length - 1,
    ];

    for (const candidate of candidates) {
        if (typeof candidate === 'number' && candidate >= 0 && candidate < allFindings.length) {
            return { finding: allFindings[candidate], index: candidate };
        }
    }

    return null;
}

export function resolvePresentedFindingIndex(
    findingResp: FindingResponse,
    allFindings: Finding[],
    currentFindingIndex: number,
    preferredIndex?: number,
): number {
    let resolvedIndex: number | undefined;

    if (findingResp.finding) {
        const matchedIndex = allFindings.findIndex((f) => f.number === findingResp.finding!.number);
        if (matchedIndex >= 0) {
            resolvedIndex = matchedIndex;
        }
    }

    // Prefer explicit backend index only when we couldn't map by finding number.
    // In some resume/view flows the backend may return a stale or missing index
    // while still returning the correct finding payload.
    if (typeof resolvedIndex !== 'number' && typeof findingResp.index === 'number') {
        resolvedIndex = findingResp.index;
    }

    if (typeof resolvedIndex !== 'number' && typeof preferredIndex === 'number') {
        resolvedIndex = preferredIndex;
    }

    if (typeof resolvedIndex !== 'number') {
        resolvedIndex = currentFindingIndex;
    }

    if (allFindings.length <= 0) {
        return Math.max(0, resolvedIndex);
    }

    if (resolvedIndex < 0) {
        return 0;
    }
    if (resolvedIndex >= allFindings.length) {
        return allFindings.length - 1;
    }
    return resolvedIndex;
}
