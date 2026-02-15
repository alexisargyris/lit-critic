/**
 * Real tests for ApiClient module.
 * 
 * Tests the actual ApiClient class with mocked http module.
 */

import { strict as assert } from 'assert';
import { 
    createFreshMockVscode, 
    MockHttpResponse, 
    MockHttpRequest,
    sampleAnalysisSummary,
    sampleServerConfig,
    sampleSessionInfo,
    sampleFindingResponse,
    sampleAdvanceResponse,
} from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

describe('ApiClient (Real)', () => {
    let ApiClient: any;
    let mockHttp: any;
    let client: any;

    beforeEach(() => {
        // Default mock http module
        mockHttp = {
            request: (options: any, callback?: any) => {
                const req = new MockHttpRequest();
                return req;
            },
        };
    });

    afterEach(() => {
        client = null;
    });

    function createClient() {
        const module = proxyquire('../../vscode-extension/src/apiClient', {
            'http': mockHttp,
        });
        ApiClient = module.ApiClient;
        client = new ApiClient('http://localhost:8000');
        return client;
    }

    describe('constructor', () => {
        it('should construct with base URL', () => {
            client = createClient();
            assert.ok(client);
        });

        it('should format request options correctly', () => {
            let capturedOptions: any;
            
            mockHttp.request = (options: any, callback?: any) => {
                capturedOptions = options;
                const req = new MockHttpRequest(new MockHttpResponse(200, {}));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            client.getConfig();
            
            assert.equal(capturedOptions.hostname, 'localhost');
            assert.equal(capturedOptions.port, '8000');
            assert.ok(capturedOptions.path);
        });
    });

    describe('GET endpoints', () => {
        it('should make GET request to /api/config', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'GET');
                assert.equal(options.path, '/api/config');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, sampleServerConfig));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.getConfig();
            
            assert.ok(result.api_key_configured);
            assert.ok(result.available_models);
            assert.equal(result.default_model, 'sonnet');
        });

        it('should make GET request to /api/session', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'GET');
                assert.equal(options.path, '/api/session');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, sampleSessionInfo));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.getSession();
            
            assert.equal(result.active, true);
            assert.equal(result.total_findings, 3);
        });

        it('should make GET request to /api/finding', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'GET');
                assert.equal(options.path, '/api/finding');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, sampleFindingResponse));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.getCurrentFinding();
            
            assert.equal(result.complete, false);
            assert.ok(result.finding);
        });

        it('should make GET request to /api/scene', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'GET');
                assert.equal(options.path, '/api/scene');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, { content: 'scene text' }));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.getScene();
            
            assert.equal(result.content, 'scene text');
        });

        it('should make GET request with URL-encoded project_path', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'GET');
                assert.ok(options.path.includes('/api/sessions'));
                assert.ok(options.path.includes('project_path='));
                assert.ok(options.path.includes('%2Ftest%2Fproject')); // encoded /test/project
                
                const req = new MockHttpRequest(new MockHttpResponse(200, { sessions: [] }));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.listSessions('/test/project');
            
            assert.ok(Array.isArray(result.sessions));
        });
    });

    describe('POST endpoints', () => {
        it('should send POST with JSON body to /api/analyze', async () => {
            let capturedBody: any;
            
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/analyze');
                assert.equal(options.headers['Content-Type'], 'application/json');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, sampleAnalysisSummary));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            await client.analyze('/test/scene.txt', '/test/project', 'sonnet');
            
            assert.equal(capturedBody.scene_path, '/test/scene.txt');
            assert.equal(capturedBody.project_path, '/test/project');
            assert.equal(capturedBody.model, 'sonnet');
        });

        it('should send POST to /api/resume', async () => {
            let capturedBody: any;
            
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/resume');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, sampleAnalysisSummary));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            await client.resume('/test/project');
            
            assert.equal(capturedBody.project_path, '/test/project');
        });

        it('should send POST to /api/resume with scene_path_override', async () => {
            let capturedBody: any;

            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/resume');

                const req = new MockHttpRequest(new MockHttpResponse(200, sampleAnalysisSummary));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };

            client = createClient();
            await client.resume('/test/project', undefined, '/test/project/scenes/ch01.md');

            assert.equal(capturedBody.project_path, '/test/project');
            assert.equal(capturedBody.scene_path_override, '/test/project/scenes/ch01.md');
        });

        it('should send POST to /api/resume-session with session_id', async () => {
            let capturedBody: any;

            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/resume-session');

                const req = new MockHttpRequest(new MockHttpResponse(200, sampleAnalysisSummary));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };

            client = createClient();
            await client.resumeSessionById('/test/project', 7);

            assert.equal(capturedBody.project_path, '/test/project');
            assert.equal(capturedBody.session_id, 7);
        });

        it('should send POST to /api/resume-session with scene_path_override', async () => {
            let capturedBody: any;

            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/resume-session');

                const req = new MockHttpRequest(new MockHttpResponse(200, sampleAnalysisSummary));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };

            client = createClient();
            await client.resumeSessionById('/test/project', 7, undefined, '/test/project/scenes/ch01.md');

            assert.equal(capturedBody.project_path, '/test/project');
            assert.equal(capturedBody.session_id, 7);
            assert.equal(capturedBody.scene_path_override, '/test/project/scenes/ch01.md');
        });

        it('should recover from scene_path_not_found in resumeWithRecovery', async () => {
            const capturedBodies: any[] = [];
            let callCount = 0;

            mockHttp.request = (options: any, callback?: any) => {
                callCount += 1;
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/resume');

                const response = callCount === 1
                    ? new MockHttpResponse(409, {
                        detail: {
                            code: 'scene_path_not_found',
                            saved_scene_path: '/old/path/ch01.md',
                            attempted_scene_path: '/old/path/ch01.md',
                        },
                    })
                    : new MockHttpResponse(200, sampleAnalysisSummary);

                const req = new MockHttpRequest(response);
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBodies.push(JSON.parse(data));
                    originalWrite(data);
                };

                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };

            client = createClient();
            const result = await client.resumeWithRecovery(
                '/test/project',
                undefined,
                async () => '/new/path/ch01.md'
            );

            assert.equal(callCount, 2);
            assert.equal(capturedBodies[0].project_path, '/test/project');
            assert.equal(capturedBodies[1].scene_path_override, '/new/path/ch01.md');
            assert.equal(result.scene_name, sampleAnalysisSummary.scene_name);
        });

        it('should recover from scene_path_not_found in resumeSessionByIdWithRecovery', async () => {
            const capturedBodies: any[] = [];
            let callCount = 0;

            mockHttp.request = (options: any, callback?: any) => {
                callCount += 1;
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/resume-session');

                const response = callCount === 1
                    ? new MockHttpResponse(409, {
                        detail: {
                            code: 'scene_path_not_found',
                            saved_scene_path: '/old/path/ch01.md',
                            attempted_scene_path: '/old/path/ch01.md',
                        },
                    })
                    : new MockHttpResponse(200, sampleAnalysisSummary);

                const req = new MockHttpRequest(response);
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBodies.push(JSON.parse(data));
                    originalWrite(data);
                };

                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };

            client = createClient();
            const result = await client.resumeSessionByIdWithRecovery(
                '/test/project',
                7,
                undefined,
                async () => '/new/path/ch01.md'
            );

            assert.equal(callCount, 2);
            assert.equal(capturedBodies[0].project_path, '/test/project');
            assert.equal(capturedBodies[0].session_id, 7);
            assert.equal(capturedBodies[1].session_id, 7);
            assert.equal(capturedBodies[1].scene_path_override, '/new/path/ch01.md');
            assert.equal(result.scene_name, sampleAnalysisSummary.scene_name);
        });

        it('should send POST to /api/finding/accept', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/finding/accept');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, sampleAdvanceResponse));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.acceptFinding();
            
            assert.ok(result);
        });

        it('should send POST to /api/finding/reject with reason', async () => {
            let capturedBody: any;
            
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/finding/reject');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, sampleAdvanceResponse));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            await client.rejectFinding('Not applicable');
            
            assert.equal(capturedBody.reason, 'Not applicable');
        });

        it('should send POST to /api/finding/discuss with message', async () => {
            let capturedBody: any;
            
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/finding/discuss');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, { 
                    response: 'AI response',
                    status: 'active',
                    finding_status: 'pending',
                }));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            await client.discuss('Can you clarify?');
            
            assert.equal(capturedBody.message, 'Can you clarify?');
        });
    });

    describe('DELETE endpoints', () => {
        it('should send DELETE to /api/session', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'DELETE');
                assert.equal(options.path, '/api/session');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, { deleted: true }));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.clearSession();
            
            assert.equal(result.deleted, true);
        });

        it('should send DELETE to /api/sessions/{id} with project_path', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'DELETE');
                assert.ok(options.path.includes('/api/sessions/5'));
                assert.ok(options.path.includes('project_path='));
                
                const req = new MockHttpRequest(new MockHttpResponse(200, { 
                    deleted: true, 
                    session_id: 5 
                }));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.deleteSession(5, '/test/project');
            
            assert.equal(result.deleted, true);
            assert.equal(result.session_id, 5);
        });
    });

    describe('error handling', () => {
        it('should reject on HTTP 500 error', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                const req = new MockHttpRequest(new MockHttpResponse(500, { 
                    detail: 'Internal server error' 
                }));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            
            await assert.rejects(
                () => client.getConfig(),
                /HTTP 500: Internal server error/
            );
        });

        it('should reject on HTTP 422 with formatted validation errors', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                const req = new MockHttpRequest(new MockHttpResponse(422, { 
                    detail: [
                        { loc: ['body', 'scene_path'], msg: 'field required' },
                        { loc: ['body', 'project_path'], msg: 'field required' },
                    ]
                }));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            
            await assert.rejects(
                () => client.analyze('', '', ''),
                /Validation error:.*scene_path.*project_path/
            );
        });

        it('should reject on network error', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                const req = new MockHttpRequest(undefined, true); // shouldError = true
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            
            await assert.rejects(
                () => client.getConfig(),
                /Network error/
            );
        });

        it('should reject on timeout', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                const req = new MockHttpRequest(undefined, false, true); // shouldTimeout = true
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            
            await assert.rejects(
                () => client.getConfig(),
                /Request timed out/
            );
        });

        it('should reject on invalid JSON response', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                // Return a response with invalid JSON
                const response = new MockHttpResponse(200, '');
                // Override body to be invalid JSON
                (response as any).body = 'not json {{{';
                
                const req = new MockHttpRequest(response);
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            
            await assert.rejects(
                () => client.getConfig(),
                /Invalid JSON response/
            );
        });
    });

    describe('SSE streaming', () => {
        it('should parse SSE events from streamDiscuss', (done) => {
            const tokens: string[] = [];
            
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/finding/discuss/stream');
                assert.equal(options.headers['Accept'], 'text/event-stream');
                
                const req = new MockHttpRequest();
                
                setImmediate(() => {
                    const res = new MockHttpResponse(200, '');
                    if (callback) {
                        callback(res);
                    }
                    
                    // Simulate SSE stream
                    setTimeout(() => {
                        res.emit('data', Buffer.from('data: {"type":"token","text":"Hello"}\n\n'));
                        res.emit('data', Buffer.from('data: {"type":"token","text":" world"}\n\n'));
                        res.emit('data', Buffer.from('data: {"type":"done","response":"Hello world","status":"active","finding_status":"pending"}\n\n'));
                        res.emit('end');
                    }, 10);
                });
                
                return req;
            };
            
            client = createClient();
            
            const abort = client.streamDiscuss(
                'test message',
                (token: string) => tokens.push(token),
                (result: any) => {
                    assert.deepEqual(tokens, ['Hello', ' world']);
                    assert.equal(result.response, 'Hello world');
                    done();
                },
                (err: Error) => done(err)
            );
        });

        it('should fire onDone callback for done events', (done) => {
            mockHttp.request = (options: any, callback?: any) => {
                const req = new MockHttpRequest();
                
                setImmediate(() => {
                    const res = new MockHttpResponse(200, '');
                    if (callback) {
                        callback(res);
                    }
                    
                    setTimeout(() => {
                        res.emit('data', Buffer.from('data: {"type":"done","response":"Complete","status":"active","finding_status":"pending"}\n\n'));
                        res.emit('end');
                    }, 10);
                });
                
                return req;
            };
            
            client = createClient();
            
            client.streamDiscuss(
                'test',
                () => {},
                (result: any) => {
                    assert.equal(result.response, 'Complete');
                    done();
                },
                (err: Error) => done(err)
            );
        });

        it('should return abort function that destroys request', () => {
            let destroyCalled = false;
            
            mockHttp.request = (options: any, callback?: any) => {
                const req = new MockHttpRequest();
                req.destroy = () => {
                    destroyCalled = true;
                };
                return req;
            };
            
            client = createClient();
            const abort = client.streamDiscuss(
                'test',
                () => {},
                () => {},
                () => {}
            );
            
            abort();
            assert.ok(destroyCalled);
        });

        it('should parse SSE events from streamAnalysisProgress', (done) => {
            const events: any[] = [];
            
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'GET');
                assert.equal(options.path, '/api/analyze/progress');
                
                const req = new MockHttpRequest();
                
                setImmediate(() => {
                    const res = new MockHttpResponse(200, '');
                    if (callback) {
                        callback(res);
                    }
                    
                    setTimeout(() => {
                        res.emit('data', Buffer.from('data: {"type":"status","message":"Starting analysis"}\n\n'));
                        res.emit('data', Buffer.from('data: {"type":"lens_complete","lens":"prose"}\n\n'));
                        res.emit('data', Buffer.from('data: {"type":"done"}\n\n'));
                        res.emit('end');
                    }, 10);
                });
                
                return req;
            };
            
            client = createClient();
            
            client.streamAnalysisProgress(
                (event: any) => events.push(event),
                () => {
                    assert.equal(events.length, 3);
                    assert.equal(events[0].type, 'status');
                    assert.equal(events[1].type, 'lens_complete');
                    assert.equal(events[2].type, 'done');
                    done();
                },
                (err: Error) => done(err)
            );
        });
    });

    describe('Management API methods', () => {
        it('should call GET /api/learning with project_path', async () => {
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'GET');
                assert.ok(options.path.includes('/api/learning'));
                assert.ok(options.path.includes('project_path='));
                
                const req = new MockHttpRequest(new MockHttpResponse(200, {
                    project_name: 'Test',
                    review_count: 0,
                    preferences: [],
                    blind_spots: [],
                    resolutions: [],
                    ambiguity_intentional: [],
                    ambiguity_accidental: [],
                }));
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.getLearning('/test/project');
            
            assert.ok(result.project_name);
            assert.ok(Array.isArray(result.preferences));
        });

        it('should call POST /api/learning/export with body', async () => {
            let capturedBody: any;
            
            mockHttp.request = (options: any, callback?: any) => {
                assert.equal(options.method, 'POST');
                assert.equal(options.path, '/api/learning/export');
                
                const req = new MockHttpRequest(new MockHttpResponse(200, {
                    exported: true,
                    path: '/test/project/LEARNING.md',
                }));
                const originalWrite = req.write.bind(req);
                req.write = (data: any) => {
                    capturedBody = JSON.parse(data);
                    originalWrite(data);
                };
                if (callback) {
                    req.on('response', callback);
                }
                return req;
            };
            
            client = createClient();
            const result = await client.exportLearning('/test/project');
            
            assert.equal(capturedBody.project_path, '/test/project');
            assert.equal(result.exported, true);
            assert.ok(result.path.endsWith('LEARNING.md'));
        });
    });
});
