/**
 * API Client — typed HTTP wrapper for all lit-critic REST endpoints.
 *
 * Uses Node's built-in http module (no external dependencies).
 * All methods return typed responses matching the Python backend.
 */

import * as http from 'http';
import {
    AnalysisSummary,
    AnalysisProgressEvent,
    CheckSessionResponse,
    DiscussResponse,
    FindingResponse,
    AdvanceResponse,
    ServerConfig,
    SessionInfo,
    SessionSummary,
    SessionDetail,
    LearningData,
    ResumeErrorDetail,
    ScenePathRecoverySelection,
    RepoPreflightStatus,
    RepoPathInvalidDetail,
    IndexAuditResponse,
    SceneAuditResponse,
    SceneProjectionResponse,
    IndexProjectionResponse,
    ProjectKnowledgeRefreshResponse,
    ProjectKnowledgeStatus,
    KnowledgeReviewResponse,
    KnowledgeOverrideResponse,
    KnowledgeOverrideDeleteResponse,
    KnowledgeEntityDeleteResponse,
    KnowledgeExportResponse,
    KnowledgeLockResponse,
    SceneLockResponse,
    SceneRenameResponse,
    SceneRefreshResponse,
    SceneOrphanPurgeResponse,
    InputStalenessResponse,
} from './types';

type LegacyIndexInsertBucket = {
    added?: unknown[];
};

type LegacyThreadIndexBucket = LegacyIndexInsertBucket & {
    advanced?: unknown[];
    closed?: unknown[];
};

type LegacyIndexSceneReport = {
    cast?: LegacyIndexInsertBucket;
    glossary?: LegacyIndexInsertBucket;
    threads?: LegacyThreadIndexBucket;
    timeline?: LegacyIndexInsertBucket;
    error?: string;
    [key: string]: unknown;
};

type LegacyIndexSceneResponse = {
    report: LegacyIndexSceneReport;
    summary: string;
};

export class ApiClient {
    private baseUrl: string;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    // ------------------------------------------------------------------
    // Generic HTTP helpers
    // ------------------------------------------------------------------

    private request<T>(method: string, path: string, body?: unknown): Promise<T> {
        return new Promise((resolve, reject) => {
            const url = new URL(path, this.baseUrl);
            const bodyStr = body !== undefined ? JSON.stringify(body) : undefined;

            const options: http.RequestOptions = {
                method,
                hostname: url.hostname,
                port: url.port,
                path: url.pathname + url.search,
                headers: {
                    'Accept': 'application/json',
                    ...(bodyStr ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(bodyStr) } : {}),
                },
                timeout: 300000, // 5 minutes — analysis can be slow
            };

            const req = http.request(options, (res) => {
                let data = '';
                res.on('data', (chunk: Buffer) => { data += chunk.toString(); });
                res.on('end', () => {
                    if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                        try {
                            resolve(JSON.parse(data) as T);
                        } catch {
                            reject(new Error(`Invalid JSON response: ${data.slice(0, 200)}`));
                        }
                    } else {
                        let detail = data;
                        try {
                            const parsed = JSON.parse(data);
                            // Handle FastAPI validation errors (422)
                            if (res.statusCode === 422 && parsed.detail && Array.isArray(parsed.detail)) {
                                // Format validation errors nicely
                                const errors = parsed.detail.map((err: any) => 
                                    `${err.loc?.join('.') || 'unknown'}: ${err.msg}`
                                ).join(', ');
                                detail = `Validation error: ${errors}`;
                            } else if (typeof parsed.detail === 'string') {
                                detail = parsed.detail;
                            } else if (typeof parsed.detail === 'object') {
                                detail = JSON.stringify(parsed.detail);
                            } else {
                                detail = data;
                            }
                        } catch {
                            // keep raw data
                        }
                        reject(new Error(`HTTP ${res.statusCode}: ${detail}`));
                    }
                });
            });

            req.on('error', reject);
            req.on('timeout', () => {
                req.destroy();
                reject(new Error('Request timed out'));
            });

            if (bodyStr) {
                req.write(bodyStr);
            }
            req.end();
        });
    }

    private extractResumeErrorDetail(message: string): ResumeErrorDetail | null {
        const match = message.match(/^HTTP\s+\d+:\s+(\{.*\})$/);
        if (!match) {
            return null;
        }

        try {
            const detail = JSON.parse(match[1]) as ResumeErrorDetail;
            if (detail && detail.code === 'scene_path_not_found') {
                return detail;
            }
        } catch {
            // ignore parse failures
        }

        return null;
    }

    private extractRepoPathInvalidDetail(message: string): RepoPathInvalidDetail | null {
        const match = message.match(/^HTTP\s+\d+:\s+(\{.*\})$/);
        if (!match) {
            return null;
        }

        try {
            const detail = JSON.parse(match[1]) as RepoPathInvalidDetail;
            if (detail && detail.code === 'repo_path_invalid') {
                return detail;
            }
        } catch {
            // ignore parse failures
        }

        return null;
    }

    /**
     * Open an SSE stream. Returns a function to abort the connection.
     * Calls `onEvent` for each parsed SSE event.
     */
    private streamSSE<T>(
        method: string,
        path: string,
        onEvent: (event: T) => void,
        onDone: () => void,
        onError: (err: Error) => void,
        body?: unknown,
    ): () => void {
        const url = new URL(path, this.baseUrl);
        const bodyStr = body !== undefined ? JSON.stringify(body) : undefined;

        const options: http.RequestOptions = {
            method,
            hostname: url.hostname,
            port: url.port,
            path: url.pathname + url.search,
            headers: {
                'Accept': 'text/event-stream',
                ...(bodyStr ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(bodyStr) } : {}),
            },
        };

        const req = http.request(options, (res) => {
            // Check for HTTP errors before attempting SSE parsing
            if (res.statusCode && (res.statusCode < 200 || res.statusCode >= 300)) {
                let errorBody = '';
                res.on('data', (chunk: Buffer) => { errorBody += chunk.toString(); });
                res.on('end', () => {
                    let detail = errorBody;
                    try {
                        const parsed = JSON.parse(errorBody);
                        detail = parsed.detail || errorBody;
                    } catch {
                        // keep raw body
                    }
                    onError(new Error(`HTTP ${res.statusCode}: ${detail}`));
                });
                return;
            }

            let buffer = '';

            res.on('data', (chunk: Buffer) => {
                buffer += chunk.toString();
                // Parse SSE lines
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // keep incomplete line in buffer

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (trimmed.startsWith('data: ')) {
                        const jsonStr = trimmed.slice(6);
                        try {
                            const event = JSON.parse(jsonStr) as T;
                            onEvent(event);
                        } catch {
                            // skip malformed events
                        }
                    }
                    // Ignore comments (: keepalive) and empty lines
                }
            });

            res.on('end', onDone);
            res.on('error', onError);
        });

        req.on('error', onError);

        if (bodyStr) {
            req.write(bodyStr);
        }
        req.end();

        return () => req.destroy();
    }

    // ------------------------------------------------------------------
    // API endpoints
    // ------------------------------------------------------------------

    /** GET /api/config — health check and config info. */
    async getConfig(): Promise<ServerConfig> {
        return this.request<ServerConfig>('GET', '/api/config');
    }

    /** GET /api/repo-preflight — get backend repo-path preflight status. */
    async getRepoPreflight(): Promise<RepoPreflightStatus> {
        return this.request<RepoPreflightStatus>('GET', '/api/repo-preflight');
    }

    /** POST /api/repo-path — validate and persist backend repo path. */
    async updateRepoPath(repoPath: string): Promise<RepoPreflightStatus> {
        return this.request<RepoPreflightStatus>('POST', '/api/repo-path', {
            repo_path: repoPath,
        });
    }

    /** POST /api/analyze — start a new analysis (single or multi-scene). */
    async analyze(
        scenePath: string,
        projectPath: string,
        apiKey?: string,
        scenePaths?: string[],
        mode?: 'quick' | 'deep',
    ): Promise<AnalysisSummary> {
        const effectivePaths = scenePaths && scenePaths.length > 0 ? scenePaths : [scenePath];
        return this.request<AnalysisSummary>('POST', '/api/analyze', {
            scene_path: effectivePaths[0],
            scene_paths: effectivePaths,
            project_path: projectPath,
            ...(apiKey ? { api_key: apiKey } : {}),
            ...(mode ? { mode } : {}),
        });
    }

    /** POST /api/config/models — persist model-slot configuration. */
    async updateConfigModels(modelSlots: { frontier: string; deep: string; quick: string }): Promise<{ model_slots: { frontier: string; deep: string; quick: string } }> {
        return this.request<{ model_slots: { frontier: string; deep: string; quick: string } }>('POST', '/api/config/models', modelSlots);
    }

    /** POST /api/config — persist scene discovery configuration. */
    async updateConfig(sceneConfig: { scene_folder: string; scene_extensions: string[] }): Promise<{
        scene_folder: string;
        scene_extensions: string[];
        default_scene_folder: string;
        default_scene_extensions: string[];
    }> {
        return this.request<{
            scene_folder: string;
            scene_extensions: string[];
            default_scene_folder: string;
            default_scene_extensions: string[];
        }>('POST', '/api/config', sceneConfig);
    }

    /** POST /api/analyze/rerun — re-run analysis for current active session context. */
    async rerunAnalysis(projectPath: string, apiKey?: string): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/analyze/rerun', {
            project_path: projectPath,
            ...(apiKey ? { api_key: apiKey } : {}),
        });
    }

    /** GET /api/analyze/progress — SSE stream for analysis progress. */
    streamAnalysisProgress(
        onEvent: (event: AnalysisProgressEvent) => void,
        onDone: () => void,
        onError: (err: Error) => void,
    ): () => void {
        return this.streamSSE<AnalysisProgressEvent>(
            'GET', '/api/analyze/progress', onEvent, onDone, onError
        );
    }

    private buildScenePathRecoveryPayload(selection?: ScenePathRecoverySelection): Record<string, unknown> {
        if (!selection) {
            return {};
        }

        return {
            ...(selection.scenePathOverride ? { scene_path_override: selection.scenePathOverride } : {}),
            ...(selection.scenePathOverrides ? { scene_path_overrides: selection.scenePathOverrides } : {}),
        };
    }

    /** POST /api/resume — resume a saved session. */
    async resume(projectPath: string, apiKey?: string, recoverySelection?: ScenePathRecoverySelection): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/resume', {
            project_path: projectPath,
            ...(apiKey ? { api_key: apiKey } : {}),
            ...this.buildScenePathRecoveryPayload(recoverySelection),
        });
    }

    /** POST /api/resume-session — resume a specific active session by id. */
    async resumeSessionById(
        projectPath: string,
        sessionId: number,
        apiKey?: string,
        recoverySelection?: ScenePathRecoverySelection,
    ): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/resume-session', {
            project_path: projectPath,
            session_id: sessionId,
            ...(apiKey ? { api_key: apiKey } : {}),
            ...this.buildScenePathRecoveryPayload(recoverySelection),
        });
    }

    /** POST /api/view-session — load any session for viewing/interaction. */
    async viewSession(
        projectPath: string,
        sessionId: number,
        apiKey?: string,
        recoverySelection?: ScenePathRecoverySelection,
        reopen: boolean = false,
    ): Promise<AnalysisSummary> {
        const response = await this.request<AnalysisSummary>('POST', '/api/view-session', {
            project_path: projectPath,
            session_id: sessionId,
            ...(apiKey ? { api_key: apiKey } : {}),
            ...(reopen ? { reopen: true } : {}),
            ...this.buildScenePathRecoveryPayload(recoverySelection),
        });

        return response;
    }

    async resumeWithRecovery(
        projectPath: string,
        apiKey: string | undefined,
        getScenePathOverride: (detail: ResumeErrorDetail) => Promise<ScenePathRecoverySelection | undefined>,
    ): Promise<AnalysisSummary> {
        try {
            return await this.resume(projectPath, apiKey);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            const detail = this.extractResumeErrorDetail(message);
            if (!detail) {
                throw err;
            }

            const selection = await getScenePathOverride(detail);
            if (!selection || (!selection.scenePathOverride?.trim() && !selection.scenePathOverrides)) {
                throw new Error('Resume cancelled by user.');
            }

            const normalized: ScenePathRecoverySelection = {
                ...(selection.scenePathOverride ? { scenePathOverride: selection.scenePathOverride.trim() } : {}),
                ...(selection.scenePathOverrides ? { scenePathOverrides: selection.scenePathOverrides } : {}),
            };

            return this.resume(projectPath, apiKey, normalized);
        }
    }

    async resumeWithRepoPathRecovery(
        projectPath: string,
        apiKey: string | undefined,
        repoPath: string,
    ): Promise<AnalysisSummary> {
        try {
            return await this.resume(projectPath, apiKey);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            const detail = this.extractRepoPathInvalidDetail(message);
            if (!detail) {
                throw err;
            }

            await this.updateRepoPath(repoPath);
            return this.resume(projectPath, apiKey);
        }
    }

    async resumeSessionByIdWithRecovery(
        projectPath: string,
        sessionId: number,
        apiKey: string | undefined,
        getScenePathOverride: (detail: ResumeErrorDetail) => Promise<ScenePathRecoverySelection | undefined>,
    ): Promise<AnalysisSummary> {
        try {
            return await this.resumeSessionById(projectPath, sessionId, apiKey);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            const detail = this.extractResumeErrorDetail(message);
            if (!detail) {
                throw err;
            }

            const selection = await getScenePathOverride(detail);
            if (!selection || (!selection.scenePathOverride?.trim() && !selection.scenePathOverrides)) {
                throw new Error('Resume cancelled by user.');
            }

            const normalized: ScenePathRecoverySelection = {
                ...(selection.scenePathOverride ? { scenePathOverride: selection.scenePathOverride.trim() } : {}),
                ...(selection.scenePathOverrides ? { scenePathOverrides: selection.scenePathOverrides } : {}),
            };

            return this.resumeSessionById(projectPath, sessionId, apiKey, normalized);
        }
    }

    async viewSessionWithRecovery(
        projectPath: string,
        sessionId: number,
        apiKey: string | undefined,
        getScenePathOverride: (detail: ResumeErrorDetail) => Promise<ScenePathRecoverySelection | undefined>,
        reopen: boolean = false,
    ): Promise<AnalysisSummary> {
        try {
            return await this.viewSession(projectPath, sessionId, apiKey, undefined, reopen);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            const detail = this.extractResumeErrorDetail(message);
            if (!detail) {
                throw err;
            }

            const selection = await getScenePathOverride(detail);
            if (!selection || (!selection.scenePathOverride?.trim() && !selection.scenePathOverrides)) {
                throw new Error('View session cancelled by user.');
            }

            const normalized: ScenePathRecoverySelection = {
                ...(selection.scenePathOverride ? { scenePathOverride: selection.scenePathOverride.trim() } : {}),
                ...(selection.scenePathOverrides ? { scenePathOverrides: selection.scenePathOverrides } : {}),
            };

            return this.viewSession(projectPath, sessionId, apiKey, normalized, reopen);
        }
    }

    /** POST /api/check-session — check if a saved session exists. */
    async checkSession(projectPath: string): Promise<CheckSessionResponse> {
        return this.request<CheckSessionResponse>('POST', '/api/check-session', {
            project_path: projectPath,
        });
    }

    /** GET /api/session — get current session info. */
    async getSession(): Promise<SessionInfo> {
        return this.request<SessionInfo>('GET', '/api/session');
    }

    /** GET /api/scene — get the scene text content. */
    async getScene(): Promise<{ content: string }> {
        return this.request<{ content: string }>('GET', '/api/scene');
    }

    /** GET /api/finding — get the current finding. */
    async getCurrentFinding(): Promise<FindingResponse> {
        return this.request<FindingResponse>('GET', '/api/finding');
    }

    /** POST /api/finding/continue — advance to next finding. */
    async continueFinding(): Promise<AdvanceResponse> {
        return this.request<AdvanceResponse>('POST', '/api/finding/continue');
    }

    /** POST /api/finding/accept — accept and advance. */
    async acceptFinding(): Promise<AdvanceResponse> {
        return this.request<AdvanceResponse>('POST', '/api/finding/accept');
    }

    /** POST /api/finding/reject — reject and advance. */
    async rejectFinding(reason: string = ''): Promise<AdvanceResponse> {
        return this.request<AdvanceResponse>('POST', '/api/finding/reject', { reason });
    }

    /** POST /api/finding/discuss — send a discussion message. */
    async discuss(message: string): Promise<DiscussResponse> {
        return this.request<DiscussResponse>('POST', '/api/finding/discuss', { message });
    }

    /** POST /api/finding/discuss/stream — SSE stream for discussion. */
    streamDiscuss(
        message: string,
        onToken: (text: string) => void,
        onDone: (result: DiscussResponse) => void,
        onError: (err: Error) => void,
        onSceneChange?: (report: { changed: boolean; adjusted: number; stale: number; re_evaluated: Array<{ finding_number: number; status: string }> }) => void,
    ): () => void {
        let receivedDone = false;

        return this.streamSSE<{ type: string; text?: string } & Partial<DiscussResponse>>(
            'POST',
            '/api/finding/discuss/stream',
            (event) => {
                if (event.type === 'scene_change' && onSceneChange) {
                    onSceneChange(event as unknown as { changed: boolean; adjusted: number; stale: number; re_evaluated: Array<{ finding_number: number; status: string }> });
                } else if (event.type === 'token' && event.text) {
                    onToken(event.text);
                } else if (event.type === 'done') {
                    receivedDone = true;
                    onDone(event as unknown as DiscussResponse);
                }
            },
            () => {
                // Transport-level stream end — if we never got a 'done' SSE
                // event, the stream closed unexpectedly (backend crash, etc.)
                if (!receivedDone) {
                    onError(new Error('Stream ended without a response. The server may have encountered an error.'));
                }
            },
            onError,
            { message },
        );
    }

    /** POST /api/finding/ambiguity — mark intentional or accidental. */
    async markAmbiguity(intentional: boolean): Promise<Record<string, unknown>> {
        return this.request<Record<string, unknown>>('POST', '/api/finding/ambiguity', { intentional });
    }

    /** POST /api/finding/goto — jump to a specific finding by index. */
    async gotoFinding(index: number): Promise<AdvanceResponse> {
        return this.request<AdvanceResponse>('POST', '/api/finding/goto', { index });
    }

    /** POST /api/finding/review — re-check current finding against scene edits. */
    async reviewFinding(): Promise<FindingResponse> {
        return this.request<FindingResponse>('POST', '/api/finding/review');
    }

    /** POST /api/finding/skip-to/{lens} — skip to a specific lens group. */
    async skipToLens(lens: 'structure' | 'coherence'): Promise<FindingResponse> {
        return this.request<FindingResponse>('POST', `/api/finding/skip-to/${lens}`);
    }

    /** DELETE /api/session — clear the session. */
    async clearSession(): Promise<{ deleted: boolean }> {
        return this.request<{ deleted: boolean }>('DELETE', '/api/session');
    }

    // ------------------------------------------------------------------
    // Management API endpoints (Phase 2)
    // ------------------------------------------------------------------

    /** GET /api/sessions — list all sessions for a project. */
    async listSessions(projectPath: string): Promise<{ sessions: SessionSummary[] }> {
        const response = await this.request<{ sessions: SessionSummary[] }>('GET', `/api/sessions?project_path=${encodeURIComponent(projectPath)}`);
        return response;
    }

    /** GET /api/sessions/{id} — get detailed info for a session. */
    async getSessionDetail(sessionId: number, projectPath: string): Promise<SessionDetail> {
        return this.request<SessionDetail>('GET', `/api/sessions/${sessionId}?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** DELETE /api/sessions/{id} — delete a session. */
    async deleteSession(sessionId: number, projectPath: string): Promise<{ deleted: boolean; session_id: number }> {
        return this.request<{ deleted: boolean; session_id: number }>('DELETE', `/api/sessions/${sessionId}?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** GET /api/learning — get learning data for a project. */
    async getLearning(projectPath: string): Promise<LearningData> {
        return this.request<LearningData>('GET', `/api/learning?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** POST /api/learning/export — export LEARNING.md. */
    async exportLearning(projectPath: string): Promise<{ exported: boolean; path: string }> {
        return this.request<{ exported: boolean; path: string }>('POST', '/api/learning/export', {
            project_path: projectPath,
        });
    }

    /** DELETE /api/learning — reset all learning data. */
    async resetLearning(projectPath: string): Promise<{ reset: boolean }> {
        return this.request<{ reset: boolean }>('DELETE', `/api/learning?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** DELETE /api/learning/entries/{id} — delete a learning entry. */
    async deleteLearningEntry(entryId: number, projectPath: string): Promise<{ deleted: boolean; entry_id: number }> {
        return this.request<{ deleted: boolean; entry_id: number }>('DELETE', `/api/learning/entries/${entryId}?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** GET /api/scenes — list projected scenes for a project. */
    async getScenes(projectPath: string): Promise<SceneProjectionResponse> {
        return this.request<SceneProjectionResponse>('GET', `/api/scenes?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** GET /api/indexes — list projected indexes for a project. */
    async getIndexes(projectPath: string): Promise<IndexProjectionResponse> {
        return this.request<IndexProjectionResponse>('GET', `/api/indexes?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** POST /api/knowledge/refresh — refresh scene + index projections and extracted knowledge. */
    async refreshKnowledge(projectPath: string): Promise<ProjectKnowledgeRefreshResponse> {
        return this.request<ProjectKnowledgeRefreshResponse>('POST', '/api/knowledge/refresh', {
            project_path: projectPath,
        });
    }

    /** Backward-compatible alias for older callers. */
    async refreshProjectKnowledge(projectPath: string): Promise<ProjectKnowledgeRefreshResponse> {
        return this.refreshKnowledge(projectPath);
    }

    /** GET /api/knowledge/review — load extracted entities + overrides for one category. */
    async getKnowledgeReview(category: string, projectPath: string): Promise<KnowledgeReviewResponse> {
        return this.request<KnowledgeReviewResponse>(
            'GET',
            `/api/knowledge/review?category=${encodeURIComponent(category)}&project_path=${encodeURIComponent(projectPath)}`,
        );
    }

    /** POST /api/knowledge/override — save one override field value. */
    async submitOverride(
        category: string,
        entityKey: string,
        fieldName: string,
        value: string,
        projectPath: string,
    ): Promise<KnowledgeOverrideResponse> {
        return this.request<KnowledgeOverrideResponse>('POST', '/api/knowledge/override', {
            category,
            entity_key: entityKey,
            field_name: fieldName,
            value,
            project_path: projectPath,
        });
    }

    /** DELETE /api/knowledge/override — delete one override field value. */
    async deleteOverride(
        category: string,
        entityKey: string,
        fieldName: string,
        projectPath: string,
    ): Promise<KnowledgeOverrideDeleteResponse> {
        return this.request<KnowledgeOverrideDeleteResponse>('DELETE', '/api/knowledge/override', {
            category,
            entity_key: entityKey,
            field_name: fieldName,
            project_path: projectPath,
        });
    }

    /** DELETE /api/knowledge/entity — delete an extracted entity and all its overrides. */
    async deleteKnowledgeEntity(
        category: string,
        entityKey: string,
        projectPath: string,
    ): Promise<KnowledgeEntityDeleteResponse> {
        return this.request<KnowledgeEntityDeleteResponse>('DELETE', '/api/knowledge/entity', {
            category,
            entity_key: entityKey,
            project_path: projectPath,
        });
    }

    /** POST /api/knowledge/export — export extracted knowledge markdown. */
    async exportKnowledge(projectPath: string): Promise<KnowledgeExportResponse> {
        return this.request<KnowledgeExportResponse>('POST', '/api/knowledge/export', {
            project_path: projectPath,
        });
    }

    /** POST /api/scenes/lock — lock one scene from automatic extraction. */
    async lockScene(sceneFilename: string, projectPath: string): Promise<SceneLockResponse> {
        return this.request<SceneLockResponse>('POST', '/api/scenes/lock', {
            scene_filename: sceneFilename,
            project_path: projectPath,
        });
    }

    /** POST /api/scenes/unlock — unlock one scene for automatic extraction. */
    async unlockScene(sceneFilename: string, projectPath: string): Promise<SceneLockResponse> {
        return this.request<SceneLockResponse>('POST', '/api/scenes/unlock', {
            scene_filename: sceneFilename,
            project_path: projectPath,
        });
    }

    /** POST /api/knowledge/lock — lock a knowledge entity from LLM updates. */
    async lockEntity(category: string, entityKey: string, projectPath: string): Promise<KnowledgeLockResponse> {
        return this.request<KnowledgeLockResponse>('POST', '/api/knowledge/lock', {
            category,
            entity_key: entityKey,
            project_path: projectPath,
        });
    }

    /** POST /api/knowledge/unlock — unlock a knowledge entity for LLM updates. */
    async unlockEntity(category: string, entityKey: string, projectPath: string): Promise<KnowledgeLockResponse> {
        return this.request<KnowledgeLockResponse>('POST', '/api/knowledge/unlock', {
            category,
            entity_key: entityKey,
            project_path: projectPath,
        });
    }

    /** POST /api/knowledge/dismiss-flag — dismiss a review flag for one entity. */
    async dismissReviewFlag(category: string, entityKey: string, projectPath: string): Promise<{ dismissed: boolean }> {
        return this.request<{ dismissed: boolean }>('POST', '/api/knowledge/dismiss-flag', {
            category,
            entity_key: entityKey,
            project_path: projectPath,
        });
    }

    /** POST /api/scenes/rename — rename one scene and propagate references. */
    async renameScene(oldName: string, newName: string, projectPath: string): Promise<SceneRenameResponse> {
        return this.request<SceneRenameResponse>('POST', '/api/scenes/rename', {
            old_filename: oldName,
            new_filename: newName,
            project_path: projectPath,
        });
    }

    /** POST /api/scenes/refresh — write discoverable scene files into scene_projection DB. */
    async refreshScenes(projectPath: string): Promise<SceneRefreshResponse> {
        return this.request<SceneRefreshResponse>('POST', '/api/scenes/refresh', {
            project_path: projectPath,
        });
    }

    /** POST /api/scenes/purge-orphans — delete DB rows for scenes no longer on disk. */
    async purgeOrphanedSceneRefs(projectPath: string): Promise<SceneOrphanPurgeResponse> {
        return this.request<SceneOrphanPurgeResponse>('POST', '/api/scenes/purge-orphans', {
            project_path: projectPath,
        });
    }

    /** GET /api/project/status — projection freshness summary. */
    async getProjectStatus(projectPath: string): Promise<ProjectKnowledgeStatus> {
        return this.request<ProjectKnowledgeStatus>('GET', `/api/project/status?project_path=${encodeURIComponent(projectPath)}`);
    }

    /** GET /api/inputs/staleness — return stale inputs and their dependent knowledge/sessions. */
    async getInputStaleness(projectPath: string): Promise<InputStalenessResponse> {
        return this.request<InputStalenessResponse>('GET', `/api/inputs/staleness?project_path=${encodeURIComponent(projectPath)}`);
    }

    /**
     * Backward-compat shim for legacy command paths; slated for removal once callers are migrated.
     */
    async indexScene(
        scenePath: string,
        projectPath: string,
        model?: string,
        apiKey?: string,
    ): Promise<LegacyIndexSceneResponse> {
        return this.request<LegacyIndexSceneResponse>('POST', '/api/index', {
            scene_path: scenePath,
            project_path: projectPath,
            ...(model ? { model } : {}),
            ...(apiKey ? { api_key: apiKey } : {}),
        });
    }

    /**
     * Backward-compat shim for legacy command paths; slated for removal once callers are migrated.
     */
    async auditIndexes(
        projectPath: string,
        deep: boolean = false,
        model?: string,
        apiKey?: string,
    ): Promise<IndexAuditResponse> {
        return this.request<IndexAuditResponse>('POST', '/api/audit', {
            project_path: projectPath,
            deep,
            ...(model ? { model } : {}),
            ...(apiKey ? { api_key: apiKey } : {}),
        });
    }

    /**
     * Backward-compat shim for legacy command paths; slated for removal once callers are migrated.
     */
    async auditScene(
        scenePath: string,
        projectPath: string,
        deep: boolean = false,
        model?: string,
        apiKey?: string,
    ): Promise<SceneAuditResponse> {
        return this.request<SceneAuditResponse>('POST', '/api/scenes/audit', {
            scene_path: scenePath,
            project_path: projectPath,
            deep,
            ...(model ? { model } : {}),
            ...(apiKey ? { api_key: apiKey } : {}),
        });
    }

}
