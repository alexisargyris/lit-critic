/**
 * TypeScript interfaces mirroring the Python backend models.
 */

/** A single editorial finding from the analysis. */
export interface Finding {
    number: number;
    severity: 'critical' | 'major' | 'minor';
    lens: string;
    location: string;
    line_start: number | null;
    line_end: number | null;
    evidence: string;
    impact: string;
    options: string[];
    flagged_by: string[];
    ambiguity_type: string | null;
    stale: boolean;

    // Discussion state (present when include_state=True)
    status?: string;
    author_response?: string;
    discussion_turns?: Array<{ role: string; content: string }>;
    revision_history?: Array<Record<string, unknown>>;
    outcome_reason?: string;
}

/** Response from GET /api/finding */
export interface FindingResponse {
    complete: boolean;
    message?: string;
    finding?: Finding;
    index?: number;
    current?: number;
    total?: number;
    is_ambiguity?: boolean;
}

/** Response from POST /api/analyze */
export interface AnalysisSummary {
    scene_path: string;
    scene_name: string;
    project_path: string;
    total_findings: number;
    current_index: number;
    skip_minor: boolean;
    glossary_issues: string[];
    counts: { critical: number; major: number; minor: number };
    lens_counts: Record<string, { critical: number; major: number; minor: number }>;
    model: { name: string; id: string; label: string };
    learning: { review_count: number; preferences: number; blind_spots: number };
    error?: string;
}

/** Response from GET /api/session */
export interface SessionInfo {
    active: boolean;
    scene_path?: string;
    scene_name?: string;
    project_path?: string;
    total_findings?: number;
    current_index?: number;
    findings_status?: Array<{
        number: number;
        severity: string;
        lens: string;
        status: string;
        location: string;
        evidence: string;
        line_start: number | null;
        line_end: number | null;
    }>;
}

/** Response from POST /api/finding/continue (and accept/reject) */
export interface AdvanceResponse {
    complete: boolean;
    message?: string;
    scene_change?: SceneChangeReport | null;
    finding?: Finding;
    index?: number;
    current?: number;
    total?: number;
    is_ambiguity?: boolean;
    // For accept/reject wrappers
    action?: Record<string, unknown>;
    next?: AdvanceResponse;
}

/** Scene change detection report */
export interface SceneChangeReport {
    changed: boolean;
    adjusted: number;
    stale: number;
    no_lines: number;
    re_evaluated: Array<{
        finding_number: number;
        status: string;
        reason?: string;
    }>;
}

/** Response from POST /api/finding/discuss */
export interface DiscussResponse {
    response: string;
    status: string;
    finding_status: string;
    finding?: Finding;
    revision_history?: Array<Record<string, unknown>>;
    error?: string;
}

/** SSE event from /api/analyze/progress */
export interface AnalysisProgressEvent {
    type: 'status' | 'lens_complete' | 'lens_error' | 'warning' | 'error' | 'complete' | 'done';
    message?: string;
    lens?: string;
    total_findings?: number;
}

/** SSE event from /api/finding/discuss/stream */
export interface DiscussStreamEvent {
    type: 'token' | 'done';
    text?: string;
    response?: string;
    status?: string;
    finding_status?: string;
    finding?: Finding;
}

/** Response from GET /api/config */
export interface ServerConfig {
    api_key_configured: boolean;
    available_models: Record<string, { label: string }>;
    default_model: string;
}

/** Response from POST /api/check-session */
export interface CheckSessionResponse {
    exists: boolean;
    scene_path?: string;
    saved_at?: string;
    current_index?: number;
    total_findings?: number;
}
