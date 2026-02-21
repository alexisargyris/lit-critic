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
    RepoPreflightStatus,
    RepoPathInvalidDetail,
} from './types';

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

    /** POST /api/analyze — start a new analysis. */
    async analyze(
        scenePath: string,
        projectPath: string,
        model?: string,
        discussionModel?: string,
        apiKey?: string,
        lensPreferences?: { preset: string; weights?: Record<string, number> },
    ): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/analyze', {
            scene_path: scenePath,
            project_path: projectPath,
            ...(model ? { model } : {}),
            ...(discussionModel ? { discussion_model: discussionModel } : {}),
            ...(apiKey ? { api_key: apiKey } : {}),
            ...(lensPreferences ? { lens_preferences: lensPreferences } : {}),
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

    /** POST /api/resume — resume a saved session. */
    async resume(projectPath: string, apiKey?: string, scenePathOverride?: string): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/resume', {
            project_path: projectPath,
            ...(apiKey ? { api_key: apiKey } : {}),
            ...(scenePathOverride ? { scene_path_override: scenePathOverride } : {}),
        });
    }

    /** POST /api/resume-session — resume a specific active session by id. */
    async resumeSessionById(
        projectPath: string,
        sessionId: number,
        apiKey?: string,
        scenePathOverride?: string,
    ): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/resume-session', {
            project_path: projectPath,
            session_id: sessionId,
            ...(apiKey ? { api_key: apiKey } : {}),
            ...(scenePathOverride ? { scene_path_override: scenePathOverride } : {}),
        });
    }

    async resumeWithRecovery(
        projectPath: string,
        apiKey: string | undefined,
        getScenePathOverride: (detail: ResumeErrorDetail) => Promise<string | undefined>,
    ): Promise<AnalysisSummary> {
        try {
            return await this.resume(projectPath, apiKey);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            const detail = this.extractResumeErrorDetail(message);
            if (!detail) {
                throw err;
            }

            const override = await getScenePathOverride(detail);
            if (!override || !override.trim()) {
                throw new Error('Resume cancelled by user.');
            }

            return this.resume(projectPath, apiKey, override.trim());
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
        getScenePathOverride: (detail: ResumeErrorDetail) => Promise<string | undefined>,
    ): Promise<AnalysisSummary> {
        try {
            return await this.resumeSessionById(projectPath, sessionId, apiKey);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            const detail = this.extractResumeErrorDetail(message);
            if (!detail) {
                throw err;
            }

            const override = await getScenePathOverride(detail);
            if (!override || !override.trim()) {
                throw new Error('Resume cancelled by user.');
            }

            return this.resumeSessionById(projectPath, sessionId, apiKey, override.trim());
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
        return this.request<{ sessions: SessionSummary[] }>('GET', `/api/sessions?project_path=${encodeURIComponent(projectPath)}`);
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
}
