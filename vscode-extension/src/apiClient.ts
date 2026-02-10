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
                            detail = parsed.detail || data;
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

    /** POST /api/analyze — start a new analysis. */
    async analyze(scenePath: string, projectPath: string, model?: string, apiKey?: string): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/analyze', {
            scene_path: scenePath,
            project_path: projectPath,
            ...(model ? { model } : {}),
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

    /** POST /api/resume — resume a saved session. */
    async resume(projectPath: string, apiKey?: string): Promise<AnalysisSummary> {
        return this.request<AnalysisSummary>('POST', '/api/resume', {
            project_path: projectPath,
            ...(apiKey ? { api_key: apiKey } : {}),
        });
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

    /** POST /api/finding/skip-minor — skip minor findings. */
    async skipMinor(): Promise<FindingResponse> {
        return this.request<FindingResponse>('POST', '/api/finding/skip-minor');
    }

    /** POST /api/finding/skip-to/{lens} — skip to a specific lens group. */
    async skipToLens(lens: 'structure' | 'coherence'): Promise<FindingResponse> {
        return this.request<FindingResponse>('POST', `/api/finding/skip-to/${lens}`);
    }

    /** POST /api/session/save — save the current session. */
    async saveSession(): Promise<{ saved: boolean; path: string }> {
        return this.request<{ saved: boolean; path: string }>('POST', '/api/session/save');
    }

    /** DELETE /api/session — clear the session. */
    async clearSession(): Promise<{ deleted: boolean }> {
        return this.request<{ deleted: boolean }>('DELETE', '/api/session');
    }

    /** POST /api/learning/save — save LEARNING.md. */
    async saveLearning(): Promise<{ saved: boolean; path: string }> {
        return this.request<{ saved: boolean; path: string }>('POST', '/api/learning/save');
    }
}
