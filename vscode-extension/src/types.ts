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
    scene_path?: string | null;
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

/** UI-only transition payload used when review re-evaluates a finding context. */
export interface DiscussionContextTransition {
    previousFinding: Finding;
    previousTurns: Array<{ role: string; content: string }>;
    note?: string;
}

export interface IndexChangeReport {
    changed: boolean;
    stale: boolean;
    changed_files: string[];
    prompt: boolean;
}

/** Response from GET /api/finding */
export interface FindingResponse {
    complete: boolean;
    message?: string;
    review?: SceneChangeReport;
    finding?: Finding;
    index?: number;
    current?: number;
    total?: number;
    is_ambiguity?: boolean;
    index_change?: IndexChangeReport | null;
}

/** Response from POST /api/analyze */
export interface AnalysisSummary {
    scene_path: string;
    scene_paths?: string[];
    scene_name: string;
    project_path: string;
    total_findings: number;
    current_index: number;
    glossary_issues: string[];
    counts: { critical: number; major: number; minor: number };
    lens_counts: Record<string, { critical: number; major: number; minor: number }>;
    model: { name: string; id: string; label: string };
    discussion_model?: { name: string; id: string; label: string } | null;
    lens_preferences?: {
        preset: string;
        weights: Record<string, number>;
    };
    learning: { review_count: number; preferences: number; blind_spots: number };
    error?: string;
    findings_status?: Array<{
        number: number;
        severity: string;
        lens: string;
        status: string;
        location: string;
        evidence: string;
        line_start: number | null;
        line_end: number | null;
        scene_path?: string | null;
    }>;
    index_context_stale?: boolean;
    index_changed_files?: string[];
    rerun_recommended?: boolean;
    index_change?: IndexChangeReport;
}

export interface ResumeErrorDetail {
    code?: string;
    message?: string;
    saved_scene_path?: string;
    attempted_scene_path?: string;
    project_path?: string;
    override_provided?: boolean;
}

export interface RepoPreflightStatus {
    ok: boolean;
    reason_code?: string | null;
    message: string;
    path?: string | null;
    marker?: string;
    configured_path?: string | null;
}

export interface RepoPathInvalidDetail extends RepoPreflightStatus {
    code?: string;
    next_action?: string;
}

/** Response from GET /api/session */
export interface SessionInfo {
    active: boolean;
    scene_path?: string;
    scene_paths?: string[];
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
    index_context_stale?: boolean;
    index_changed_files?: string[];
    rerun_recommended?: boolean;
    index_change?: IndexChangeReport;
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
    index_change?: IndexChangeReport | null;
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
    index_change?: IndexChangeReport | null;
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
    lens_presets?: Record<string, Record<string, number>>;
}

/** Response from POST /api/check-session */
export interface CheckSessionResponse {
    exists: boolean;
    session_id?: number;
    scene_path?: string;
    saved_at?: string;
    current_index?: number;
    total_findings?: number;
}

/** Session summary from GET /api/sessions */
export interface SessionSummary {
    id: number;
    status: 'active' | 'completed' | 'abandoned';
    scene_path: string;
    scene_paths?: string[];
    model: string;
    created_at: string;
    completed_at?: string;
    total_findings: number;
    accepted_count: number;
    rejected_count: number;
    withdrawn_count: number;
    index_context_stale?: boolean;
    index_changed_files?: string[];
    rerun_recommended?: boolean;
}

/** Session detail from GET /api/sessions/{id} */
export interface SessionDetail extends SessionSummary {
    scene_hash: string;
    current_index: number;
    glossary_issues: string[];
    findings: Array<{
        id: number;
        number: number;
        severity: string;
        lens: string;
        status: string;
        location: string;
        evidence: string;
        impact?: string;
        options?: string[];
        flagged_by?: string[];
        author_response?: string;
        discussion_turns?: Array<{ role: string; content: string }>;
        revision_history?: Array<Record<string, unknown>>;
        outcome_reason?: string;
        line_start: number | null;
        line_end: number | null;
    }>;
}

/** Learning data from GET /api/learning */
export interface LearningData {
    project_name: string;
    review_count: number;
    preferences: Array<{ id?: number; description: string; created_at?: string }>;
    blind_spots: Array<{ id?: number; description: string; created_at?: string }>;
    resolutions: Array<{ id?: number; description: string; created_at?: string }>;
    ambiguity_intentional: Array<{ id?: number; description: string; created_at?: string }>;
    ambiguity_accidental: Array<{ id?: number; description: string; created_at?: string }>;
}
