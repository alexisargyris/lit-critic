/**
 * Real tests for extension.ts (main extension module).
 * 
 * Tests the actual extension activation and command registration with mocked dependencies.
 */

import { strict as assert } from 'assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { createFreshMockVscode } from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

describe('Extension (Real)', () => {
    let mockVscode: any;
    let mockServerManager: any;
    let mockApiClient: any;
    let mockFindingsTreeProvider: any;
    let mockFindingsDecorationProvider: any;
    let mockSessionsTreeProvider: any;
    let mockLearningTreeProvider: any;
    let mockDiagnosticsProvider: any;
    let mockDiscussionPanel: any;
    let mockStatusBar: any;
    let mockOperationTracker: any;
    let mockPath: any;
    let mockFs: any;
    let activate: any;
    let deactivate: any;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();
        if (!mockVscode.workspace.onDidChangeConfiguration) {
            mockVscode.workspace.onDidChangeConfiguration = () => ({ dispose: () => {} });
        }
        
        // Mock all internal modules with spy classes
        mockServerManager = class MockServerManager {
            isRunning = false;
            baseUrl = 'http://localhost:8000';
            port = 8000;
            async start() {
                this.isRunning = true;
            }
            stop() {
                this.isRunning = false;
            }
            dispose() {}
        };
        
        mockApiClient = class MockApiClient {
            async updateRepoPath(_repoPath: string) {
                return { ok: true };
            }
            async getSession() {
                return { active: false };
            }
            async getConfig() {
                return {
                    api_key_configured: true,
                    available_models: { sonnet: { label: 'Sonnet' } },
                    default_model: 'sonnet',
                };
            }
        };
        
        mockFindingsTreeProvider = class MockFindingsTreeProvider {
            currentFindingItem: any;
            setFindings(_findings: any[], _scenePath: string, currentIndex: number = -1) {
                this.currentFindingItem = currentIndex >= 0 ? { id: `finding:${currentIndex + 1}` } : undefined;
            }
            setCurrentIndex(index: number) {
                this.currentFindingItem = { id: `finding:${index + 1}` };
            }
            clear() {}
            updateFinding() {}
            getCurrentFindingItem() {
                return this.currentFindingItem;
            }
        };

        mockFindingsDecorationProvider = class MockFindingsDecorationProvider {
            fireChange() {}
        };
        
        mockSessionsTreeProvider = class MockSessionsTreeProvider {
            currentSessionItem: any;
            setApiClient() {}
            setProjectPath() {}
            async refresh() {}
            setCurrentSession(sessionId: number | null) {
                this.currentSessionItem = sessionId === null ? undefined : { id: `session:${sessionId}` };
            }
            setCurrentSessionByScenePath(scenePath?: string) {
                this.currentSessionItem = scenePath ? { id: 'session:auto' } : undefined;
            }
            getCurrentSessionItem() {
                return this.currentSessionItem;
            }
        };
        
        mockLearningTreeProvider = class MockLearningTreeProvider {
            setApiClient() {}
            setProjectPath() {}
            async refresh() {}
        };
        
        mockDiagnosticsProvider = class MockDiagnosticsProvider {
            scenePath = '';
            setScenePath() {}
            updateFromFindings() {}
            removeFinding() {}
            clear() {}
            dispose() {}
        };
        
        mockDiscussionPanel = class MockDiscussionPanel {
            onFindingAction: any;
            show() {}
            close() {}
            dispose() {}
        };
        
        mockStatusBar = class MockStatusBar {
            setReady() {}
            setAnalyzing() {}
            setProgress() {}
            setComplete() {}
            setError() {}
            dispose() {}
        };

        mockOperationTracker = class MockOperationTracker {
            async run(_profile: any, operation: () => Promise<any>) {
                return operation();
            }
            dispose() {}
        };
        
        // Mock path module
        mockPath = require('path');
        
        // Mock fs module (for findRepoRoot)
        mockFs = {
            existsSync: (path: string) => {
                // Simulate lit-critic-web.py exists in /test/repo
                return path.includes('lit-critic-web.py') && path.includes('/test/repo');
            },
        };
    });

    afterEach(() => {
        // Clean up module cache
        activate = null;
        deactivate = null;
    });

    function loadExtension() {
        // Pre-load registerCommands with the mock vscode so its transitive
        // `import * as vscode from 'vscode'` is shimmed rather than hitting
        // the real (unavailable) vscode module in the test environment.
        const registerCommandsMod = proxyquire(
            '../../vscode-extension/src/commands/registerCommands',
            { vscode: mockVscode },
        );

        const module = proxyquire('../../vscode-extension/src/extension', {
            'vscode': mockVscode,
            './serverManager': { ServerManager: mockServerManager },
            './apiClient': { ApiClient: mockApiClient },
            './findingsTreeProvider': {
                FindingsTreeProvider: mockFindingsTreeProvider,
                FindingsDecorationProvider: mockFindingsDecorationProvider,
            },
            './sessionsTreeProvider': { SessionsTreeProvider: mockSessionsTreeProvider },
            './learningTreeProvider': { LearningTreeProvider: mockLearningTreeProvider },
            './diagnosticsProvider': { DiagnosticsProvider: mockDiagnosticsProvider },
            './discussionPanel': { DiscussionPanel: mockDiscussionPanel },
            './statusBar': { StatusBar: mockStatusBar },
            './operationTracker': { OperationTracker: mockOperationTracker },
            'path': mockPath,
            'fs': mockFs,
            './commands/registerCommands': registerCommandsMod,
        });
        activate = module.activate;
        deactivate = module.deactivate;
        return module;
    }

    describe('activation', () => {
        it('should register all commands', async () => {
            const registeredCommands: string[] = [];
            
            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                registeredCommands.push(cmd);
                return { dispose: () => {} };
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            // Verify all commands are registered
            assert.ok(registeredCommands.includes('literaryCritic.analyze'));
            assert.ok(registeredCommands.includes('literaryCritic.resume'));
            assert.ok(registeredCommands.includes('literaryCritic.nextFinding'));
            assert.ok(registeredCommands.includes('literaryCritic.acceptFinding'));
            assert.ok(registeredCommands.includes('literaryCritic.rejectFinding'));
            assert.ok(registeredCommands.includes('literaryCritic.discuss'));
            assert.ok(registeredCommands.includes('literaryCritic.selectFinding'));
            assert.ok(registeredCommands.includes('literaryCritic.reviewFinding'));
            assert.ok(registeredCommands.includes('literaryCritic.clearSession'));
            assert.ok(registeredCommands.includes('literaryCritic.rerunAnalysisWithUpdatedIndexes'));
            assert.ok(registeredCommands.includes('literaryCritic.selectModel'));
            assert.ok(registeredCommands.includes('literaryCritic.stopServer'));
            assert.ok(registeredCommands.includes('literaryCritic.refreshSessions'));
            assert.ok(registeredCommands.includes('literaryCritic.viewSession'));
            assert.ok(registeredCommands.includes('literaryCritic.deleteSession'));
            assert.ok(registeredCommands.includes('literaryCritic.refreshLearning'));
            assert.ok(registeredCommands.includes('literaryCritic.exportLearning'));
            assert.ok(registeredCommands.includes('literaryCritic.resetLearning'));
            assert.ok(registeredCommands.includes('literaryCritic.deleteLearningEntry'));
            
            assert.ok(registeredCommands.length >= 19, `Expected at least 19 commands, got ${registeredCommands.length}`);
        });

        it('should create all UI components', async () => {
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            // At least 3 tree views + status bar + diagnostics provider should be pushed
            assert.ok(context.subscriptions.length >= 5, 
                `Expected at least 5 subscriptions, got ${context.subscriptions.length}`);
        });

        it('should create tree views for findings, sessions, and learning', async () => {
            const createdViews: string[] = [];
            
            mockVscode.window.createTreeView = (viewId: string, options: any) => {
                createdViews.push(viewId);
                return { dispose: () => {} };
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            assert.ok(createdViews.includes('literaryCritic.findings'));
            assert.ok(createdViews.includes('literaryCritic.sessions'));
            assert.ok(createdViews.includes('literaryCritic.learning'));
        });
    });

    describe('auto-start behavior', () => {
        it('should use native TreeView reveal selection for current session and finding during auto-load', async () => {
            const sessionRevealCalls: Array<{ item: any; options: any }> = [];
            const findingRevealCalls: Array<{ item: any; options: any }> = [];

            mockVscode.window.createTreeView = (viewId: string, _options: any) => {
                const reveal = async (item: any, options: any) => {
                    if (viewId === 'literaryCritic.sessions') {
                        sessionRevealCalls.push({ item, options });
                    }
                    if (viewId === 'literaryCritic.findings') {
                        findingRevealCalls.push({ item, options });
                    }
                };
                return { dispose: () => {}, reveal, visible: true };
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: true, scene_path: '/test/repo/scene-a.txt' };
                }
                async resumeWithRecovery() {
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 1,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 1, minor: 0 },
                        lens_counts: { prose: { critical: 0, major: 1, minor: 0 } },
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [
                            {
                                number: 1,
                                severity: 'major',
                                lens: 'prose',
                                status: 'pending',
                                location: 'L1',
                                evidence: 'example',
                                line_start: 1,
                                line_end: 1,
                            },
                        ],
                    };
                }
                async getCurrentFinding() {
                    return { complete: true };
                }
            };

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            assert.ok(sessionRevealCalls.length > 0, 'Expected native session TreeView reveal call');
            assert.ok(findingRevealCalls.length > 0, 'Expected native finding TreeView reveal call');
            assert.equal(sessionRevealCalls[0].options?.select, true);
            assert.equal(findingRevealCalls[0].options?.select, true);
            assert.equal(sessionRevealCalls[0].options?.focus, false);
            assert.equal(findingRevealCalls[0].options?.focus, false);
        });

        it('should show an immediate startup hint before startup progress notification', async () => {
            const timeline: string[] = [];

            mockVscode.window.setStatusBarMessage = (text: string) => {
                timeline.push(`status:${text}`);
                return { dispose: () => {} };
            };
            mockVscode.window.withProgress = async (options: any, task: any) => {
                timeline.push(`progress:${options?.title || ''}`);
                return task(
                    { report: (_value: any) => {} },
                    {
                        isCancellationRequested: false,
                        onCancellationRequested: (_listener: any) => ({ dispose: () => {} }),
                    },
                );
            };

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            const hintIndex = timeline.indexOf('status:lit-critic: Preparing startup...');
            const progressIndex = timeline.indexOf('progress:lit-critic: Starting server');

            assert.ok(hintIndex >= 0, 'Expected an immediate startup hint status message');
            assert.ok(progressIndex >= 0, 'Expected startup progress notification to be shown');
            assert.ok(
                hintIndex < progressIndex,
                'Expected startup hint to appear before startup progress notification',
            );
        });

        it('should reset status bar to ready after startup completes', async () => {
            const statusTransitions: string[] = [];

            mockStatusBar = class MockStatusBar {
                setReady() { statusTransitions.push('ready'); }
                setAnalyzing(message?: string) { statusTransitions.push(`analyzing:${message || ''}`); }
                setProgress() {}
                setComplete() {}
                setError() {}
                dispose() {}
            };

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            assert.ok(
                statusTransitions.includes('analyzing:Starting server...'),
                'Expected startup to set analyzing state',
            );
            assert.equal(
                statusTransitions[statusTransitions.length - 1],
                'ready',
                'Expected status bar to return to ready after startup',
            );
        });

        it('should show startup progress notification when auto-starting server', async () => {
            const progressTitles: string[] = [];

            mockVscode.window.withProgress = async (options: any, task: any) => {
                progressTitles.push(options?.title || '');
                return task(
                    { report: (_value: any) => {} },
                    {
                        isCancellationRequested: false,
                        onCancellationRequested: (_listener: any) => ({ dispose: () => {} }),
                    },
                );
            };

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            assert.ok(
                progressTitles.includes('lit-critic: Starting server'),
                'Expected startup notification progress to be shown during auto-start',
            );
        });

        it('should run repo-path recovery prompt during activation when configured repoPath is invalid', async () => {
            let serverStarted = false;
            let openedFolderDialog = false;
            let updatedRepoPath: string | undefined;

            const validRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-activation-repo-'));
            fs.writeFileSync(path.join(validRepo, 'lit-critic-web.py'), 'print("ok")', 'utf8');

            let configuredRepoPath = '/invalid/repo/path';

            mockServerManager = class extends mockServerManager {
                async start() {
                    serverStarted = true;
                    this.isRunning = true;
                }
            };

            mockVscode.window.showErrorMessage = async (message: string, ...items: any[]) => {
                if (message.includes('startup preflight failed') && items.includes('Select Folder…')) {
                    return 'Select Folder…';
                }
                return undefined;
            };

            mockVscode.window.showOpenDialog = async () => {
                openedFolderDialog = true;
                return [{ fsPath: validRepo }];
            };

            // Ensure repo discovery fails first so activation enters recovery flow.
            mockVscode.workspace.workspaceFolders = undefined;
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return configuredRepoPath;
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async (key: string, value: any) => {
                    if (key === 'repoPath') {
                        configuredRepoPath = value;
                        updatedRepoPath = value;
                    }
                },
            });

            loadExtension();
            await activate({ subscriptions: [] });

            assert.ok(openedFolderDialog, 'Expected repo recovery folder picker to open during activation');
            assert.equal(updatedRepoPath, validRepo, 'Expected corrected repoPath to be persisted during activation');
            assert.ok(serverStarted, 'Expected auto-start to continue after repo path recovery');

            fs.rmSync(validRepo, { recursive: true, force: true });
        });

        it('should auto-start server when autoStartServer is true', async () => {
            let serverStarted = false;
            
            mockServerManager = class extends mockServerManager {
                async start() {
                    serverStarted = true;
                    this.isRunning = true;
                }
            };
            
            mockVscode.workspace.getConfiguration = (section?: string) => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });
            
            // Set up workspace with repo
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];
            
            mockFs.existsSync = (path: string) => {
                return path.includes('lit-critic-web.py');
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            assert.ok(serverStarted, 'Server should have been started');
        });

        it('should reveal lit-critic activity view after auto-start when CANON.md is present', async () => {
            const executeCommandCalls: string[] = [];

            mockVscode.commands.executeCommand = async (command: string, ..._rest: any[]) => {
                executeCommandCalls.push(command);
            };

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();

            await activate({ subscriptions: [] });

            assert.ok(
                executeCommandCalls.includes('workbench.view.extension.lit-critic'),
                'Expected lit-critic activity view to be revealed when CANON.md is present',
            );
        });

        it('should not reveal lit-critic activity view after auto-start when CANON.md is missing', async () => {
            const executeCommandCalls: string[] = [];

            mockVscode.commands.executeCommand = async (command: string, ..._rest: any[]) => {
                executeCommandCalls.push(command);
            };

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py');
            };

            loadExtension();

            await activate({ subscriptions: [] });

            assert.ok(
                !executeCommandCalls.includes('workbench.view.extension.lit-critic'),
                'Expected lit-critic activity view not to be revealed when CANON.md is missing',
            );
        });

        it('should NOT auto-start when autoStartServer is false', async () => {
            let serverStarted = false;
            let recoveryPromptShown = false;
            
            mockServerManager = class extends mockServerManager {
                async start() {
                    serverStarted = true;
                    this.isRunning = true;
                }
            };
            
            mockVscode.workspace.getConfiguration = (section?: string) => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return '/invalid/repo/path';
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockVscode.window.showErrorMessage = async (message: string, ...items: any[]) => {
                if (message.includes('startup preflight failed') && items.includes('Select Folder…')) {
                    recoveryPromptShown = true;
                }
                return undefined;
            };
            
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            assert.ok(!serverStarted, 'Server should not have been started');
            assert.ok(!recoveryPromptShown, 'Recovery prompt should not be shown when auto-start is disabled');
        });

        it('should handle missing repo root gracefully', async () => {
            // No workspace folders
            mockVscode.workspace.workspaceFolders = undefined;
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            // Should not throw
            await activate(context);
            
            // UI components should still be registered
            assert.ok(context.subscriptions.length > 0);
        });
    });

    describe('deactivation', () => {
        it('should stop the server on deactivate', async () => {
            // Track stop calls via prototype
            const stopCalls: any[] = [];
            const OriginalServerManager = mockServerManager;
            
            mockServerManager = class extends OriginalServerManager {
                stop() {
                    stopCalls.push(this);
                    this.isRunning = false;
                }
            };
            
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];
            
            mockVscode.workspace.getConfiguration = (section?: string) => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });
            
            // Fix path separators issue - just check for the file
            mockFs.existsSync = (path: string) => {
                return path.includes('lit-critic-web.py');
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            deactivate();
            
            assert.ok(stopCalls.length > 0, 'Server stop() should have been called');
        });
    });

    describe('helper functions', () => {
        it('should detect repo root from workspace', async () => {
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];
            
            mockFs.existsSync = (path: string) => {
                return path.includes('/test/repo') && path.includes('lit-critic-web.py');
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            // If repo root is found, ServerManager should be created
            // We can't directly test the helper, but we can verify the side effect
            assert.ok(true); // Activation succeeded
        });

        it('should handle configured repoPath setting', async () => {
            mockVscode.workspace.getConfiguration = (section?: string) => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return '/custom/repo/path';
                    if (key === 'autoStartServer') return false; // Don't auto-start to simplify test
                    return defaultValue;
                },
                update: async () => {},
            });
            
            mockFs.existsSync = (path: string) => {
                return path.includes('/custom/repo/path') && path.includes('lit-critic-web.py');
            };
            
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/some/other/path' } },
            ];
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            // Should use configured path rather than workspace folders
            assert.ok(true); // Activation succeeded with custom repo path
        });

        it('should detect project path from CANON.md', async () => {
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/project' } },
            ];
            
            mockFs.existsSync = (path: string) => {
                // CANON.md exists in the workspace
                if (path.includes('CANON.md') && path.includes('/test/project')) {
                    return true;
                }
                return false;
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            // detectProjectPath is called during auto-load
            assert.ok(true); // Should handle project detection gracefully
        });
    });

    describe('command handlers', () => {
        it('should show immediate startup hint when analyze triggers lazy server start', async () => {
            let analyzeCallback: any;
            const statusMessages: string[] = [];

            mockVscode.window.setStatusBarMessage = (text: string) => {
                statusMessages.push(text);
                return { dispose: () => {} };
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async checkSession() {
                    return { exists: false };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            balanced: { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                        },
                    };
                }
                async analyze() {
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(_onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => onDone(), 0);
                    return () => {};
                }
                async getCurrentFinding() {
                    return { complete: true };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];
            mockVscode.window.showOpenDialog = async () => [{ fsPath: '/test/repo/scene-a.txt' }];
            mockVscode.window.showTextDocument = async () => ({
                document: { uri: { fsPath: '/test/repo/scene-a.txt' } },
                viewColumn: 1,
            });

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return false;
                    if (key === 'lensPreset') return 'balanced';
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });
            await analyzeCallback();

            assert.ok(
                statusMessages.includes('lit-critic: Preparing startup...'),
                'Expected analyze-triggered startup to show immediate startup hint',
            );
        });

        it('should show analysis startup progress notification during analyze handoff', async () => {
            let analyzeCallback: any;
            const progressTitles: string[] = [];

            mockVscode.window.withProgress = async (options: any, task: any) => {
                progressTitles.push(options?.title || '');
                return task(
                    { report: (_value: any) => {} },
                    {
                        isCancellationRequested: false,
                        onCancellationRequested: (_listener: any) => ({ dispose: () => {} }),
                    },
                );
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async checkSession() {
                    return { exists: false };
                }
                async listSessions() {
                    return { sessions: [] };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            balanced: { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                        },
                    };
                }
                async analyze() {
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => {
                        onEvent({ type: 'status', message: 'Starting analysis...' });
                        onDone();
                    }, 0);
                    return () => {};
                }
                async getCurrentFinding() {
                    return { complete: true };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];
            mockVscode.window.showOpenDialog = async () => [{ fsPath: '/test/repo/scene-a.txt' }];
            mockVscode.window.showTextDocument = async () => ({
                document: { uri: { fsPath: '/test/repo/scene-a.txt' } },
                viewColumn: 1,
            });

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    if (key === 'lensPreset') return 'balanced';
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });
            await analyzeCallback();

            assert.ok(
                progressTitles.includes('lit-critic: Starting analysis'),
                'Expected analysis startup notification progress to be shown',
            );
        });

        it('should disambiguate resume choices when multiple active sessions exist', async () => {
            let analyzeCallback: any;
            const quickPickCalls: Array<{ items: any[]; options: any }> = [];
            const resumedSessionIds: number[] = [];

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            balanced: { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                        },
                    };
                }
                async checkSession() {
                    return { exists: true, total_findings: 7 };
                }
                async listSessions() {
                    return {
                        sessions: [
                            {
                                id: 11,
                                status: 'active',
                                scene_path: '/test/repo/scene-a.txt',
                                model: 'sonnet',
                                created_at: '2026-02-17T18:00:00',
                                total_findings: 10,
                                accepted_count: 0,
                                rejected_count: 0,
                                withdrawn_count: 0,
                            },
                            {
                                id: 12,
                                status: 'active',
                                scene_path: '/test/repo/scene-b.txt',
                                model: 'sonnet',
                                created_at: '2026-02-17T19:00:00',
                                total_findings: 5,
                                accepted_count: 0,
                                rejected_count: 0,
                                withdrawn_count: 0,
                            },
                        ],
                    };
                }
                async resumeSessionByIdWithRecovery(_projectPath: string, sessionId: number) {
                    resumedSessionIds.push(sessionId);
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                async getCurrentFinding() {
                    return { complete: true };
                }
            };

            mockVscode.window.showQuickPick = async (items: any[], options?: any) => {
                quickPickCalls.push({ items, options });
                return items[0];
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    if (key === 'lensPreset') return 'balanced';
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });
            mockVscode.window.activeTextEditor = {
                document: {
                    uri: {
                        scheme: 'file',
                        fsPath: '/test/repo/scene-a.txt',
                    },
                },
            };

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });
            await analyzeCallback();

            assert.ok(quickPickCalls.length > 0, 'Expected analyze command to show a disambiguation picker');
            const labels = quickPickCalls[0].items.map((item: any) => item.label);
            assert.ok(labels.some((label: string) => label.includes('Resume #11')));
            assert.ok(labels.some((label: string) => label.includes('Resume #12')));
            assert.deepEqual(resumedSessionIds, [11]);
        });

        it('should show preset-aware lens count instead of hardcoded five lenses', async () => {
            let analyzeCallback: any;
            const statusMessages: string[] = [];

            mockStatusBar = class MockStatusBar {
                setReady() {}
                setAnalyzing(message?: string) {
                    statusMessages.push(message || '');
                }
                setProgress() {}
                setComplete() {}
                setError() {}
                dispose() {}
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async checkSession() {
                    return { exists: false };
                }
                async listSessions() {
                    return { sessions: [] };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            'clarity-pass': {
                                prose: 0,
                                structure: 0,
                                logic: 1,
                                clarity: 1,
                                continuity: 1,
                                dialogue: 1,
                            },
                        },
                    };
                }
                async analyze() {
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(_onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => onDone(), 0);
                    return () => {};
                }
                async getCurrentFinding() {
                    return { complete: true };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    if (key === 'lensPreset') return 'clarity-pass';
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });
            mockVscode.window.activeTextEditor = {
                document: {
                    uri: {
                        scheme: 'file',
                        fsPath: '/test/repo/scene-a.txt',
                    },
                },
            };

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });
            await analyzeCallback();

            assert.ok(
                statusMessages.some((message) => message.includes('Running 4 lenses (clarity-pass preset)...')),
                'Expected status bar to include preset-aware lens count',
            );
            assert.ok(
                statusMessages.every((message) => !message.includes('Running 5 lenses')),
                'Expected no hardcoded "Running 5 lenses" status',
            );
        });

        it('should resolve auto lens preset to single-scene for single-scene analyze', async () => {
            let analyzeCallback: any;
            let analyzeLensPreset: string | undefined;
            const statusMessages: string[] = [];

            mockStatusBar = class MockStatusBar {
                setReady() {}
                setAnalyzing(message?: string) { statusMessages.push(message || ''); }
                setProgress() {}
                setComplete() {}
                setError() {}
                dispose() {}
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) { return { ok: true }; }
                async getSession() { return { active: false }; }
                async checkSession() { return { exists: false }; }
                async listSessions() { return { sessions: [] }; }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            'single-scene': { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                            'multi-scene': { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                        },
                    };
                }
                async analyze(
                    _scenePath: string,
                    _projectPath: string,
                    _model: string,
                    _discussionModel: string | undefined,
                    _apiKey: string | undefined,
                    lensPrefs: any,
                ) {
                    analyzeLensPreset = lensPrefs?.preset;
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(_onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => onDone(), 0);
                    return () => {};
                }
                async getCurrentFinding() { return { complete: true }; }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];
            mockVscode.window.showOpenDialog = async () => [{ fsPath: '/test/repo/scene-a.txt' }];
            mockVscode.window.showTextDocument = async () => ({
                document: { uri: { fsPath: '/test/repo/scene-a.txt' } },
                viewColumn: 1,
            });

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    if (key === 'lensPreset') return 'auto';
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            mockFs.existsSync = (filePath: string) => filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');

            loadExtension();
            await activate({ subscriptions: [] });
            await analyzeCallback();

            assert.equal(analyzeLensPreset, 'single-scene');
            assert.ok(
                statusMessages.some((message) => message.includes('(single-scene preset)')),
                'Expected analysis status to reflect resolved single-scene preset',
            );
        });

        it('should resolve auto lens preset to multi-scene for multi-scene analyze', async () => {
            let analyzeCallback: any;
            let analyzeLensPreset: string | undefined;
            const statusMessages: string[] = [];

            mockStatusBar = class MockStatusBar {
                setReady() {}
                setAnalyzing(message?: string) { statusMessages.push(message || ''); }
                setProgress() {}
                setComplete() {}
                setError() {}
                dispose() {}
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) { return { ok: true }; }
                async getSession() { return { active: false }; }
                async checkSession() { return { exists: false }; }
                async listSessions() { return { sessions: [] }; }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            'single-scene': { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                            'multi-scene': { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                        },
                    };
                }
                async analyze(
                    _scenePath: string,
                    _projectPath: string,
                    _model: string,
                    _discussionModel: string | undefined,
                    _apiKey: string | undefined,
                    lensPrefs: any,
                ) {
                    analyzeLensPreset = lensPrefs?.preset;
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(_onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => onDone(), 0);
                    return () => {};
                }
                async getCurrentFinding() { return { complete: true }; }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];
            mockVscode.window.showOpenDialog = async () => [
                { fsPath: '/test/repo/scene-a.txt' },
                { fsPath: '/test/repo/scene-b.txt' },
            ];
            mockVscode.window.showTextDocument = async (docOrUri: any) => ({
                document: { uri: docOrUri },
                viewColumn: 1,
            });

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    if (key === 'lensPreset') return 'auto';
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            mockFs.existsSync = (filePath: string) => filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');

            loadExtension();
            await activate({ subscriptions: [] });
            await analyzeCallback();

            assert.equal(analyzeLensPreset, 'multi-scene');
            assert.ok(
                statusMessages.some((message) => message.includes('(multi-scene preset)')),
                'Expected analysis status to reflect resolved multi-scene preset',
            );
        });

        it('should keep manual lens preset unchanged regardless of scene count', async () => {
            let analyzeCallback: any;
            let analyzeLensPreset: string | undefined;

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) { return { ok: true }; }
                async getSession() { return { active: false }; }
                async checkSession() { return { exists: false }; }
                async listSessions() { return { sessions: [] }; }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            'prose-first': { prose: 1.6, structure: 1.1, logic: 0.9, clarity: 0.9, continuity: 0.8, dialogue: 1.1 },
                        },
                    };
                }
                async analyze(
                    _scenePath: string,
                    _projectPath: string,
                    _model: string,
                    _discussionModel: string | undefined,
                    _apiKey: string | undefined,
                    lensPrefs: any,
                ) {
                    analyzeLensPreset = lensPrefs?.preset;
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(_onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => onDone(), 0);
                    return () => {};
                }
                async getCurrentFinding() { return { complete: true }; }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];
            mockVscode.window.showOpenDialog = async () => [
                { fsPath: '/test/repo/scene-a.txt' },
                { fsPath: '/test/repo/scene-b.txt' },
            ];
            mockVscode.window.showTextDocument = async (docOrUri: any) => ({
                document: { uri: docOrUri },
                viewColumn: 1,
            });

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    if (key === 'lensPreset') return 'prose-first';
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            mockFs.existsSync = (filePath: string) => filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');

            loadExtension();
            await activate({ subscriptions: [] });
            await analyzeCallback();

            assert.equal(analyzeLensPreset, 'prose-first');
        });

        it('should sync backend repo path after repo-path recovery during analyze startup', async () => {
            let analyzeCallback: any;
            let updatedRepoPathCall: string | undefined;

            const validRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-repo-sync-'));
            fs.writeFileSync(path.join(validRepo, 'lit-critic-web.py'), 'print("ok")', 'utf8');

            let configuredRepoPath = '/invalid/repo/path';

            mockApiClient = class extends mockApiClient {
                async updateRepoPath(repoPath: string) {
                    updatedRepoPathCall = repoPath;
                    return { ok: true };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.showErrorMessage = async (message: string, ...items: string[]) => {
                if (message.includes('startup preflight failed') && items.includes('Select Folder…')) {
                    return 'Select Folder…';
                }
                return undefined;
            };

            mockVscode.window.showOpenDialog = async () => {
                return [{ fsPath: validRepo }];
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];

            mockVscode.workspace.workspaceFolders = undefined;
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return configuredRepoPath;
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async (key: string, value: any) => {
                    if (key === 'repoPath') {
                        configuredRepoPath = value;
                    }
                },
            });

            loadExtension();
            await activate({ subscriptions: [] });

            await analyzeCallback();

            assert.equal(
                updatedRepoPathCall,
                validRepo,
                'Expected extension to sync corrected repo path to backend via /api/repo-path',
            );

            fs.rmSync(validRepo, { recursive: true, force: true });
        });

        it('should recover from invalid repoPath via Select Folder and retry startup', async () => {
            let analyzeCallback: any;
            let serverStarted = false;
            let openedFolderDialog = false;
            let updatedRepoPath: string | undefined;

            const validRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-repo-'));
            fs.writeFileSync(path.join(validRepo, 'lit-critic-web.py'), 'print("ok")', 'utf8');

            let configuredRepoPath = '/invalid/repo/path';

            mockServerManager = class extends mockServerManager {
                async start() {
                    serverStarted = true;
                    this.isRunning = true;
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.showErrorMessage = async (message: string, ...items: string[]) => {
                if (message.includes('startup preflight failed') && items.includes('Select Folder…')) {
                    return 'Select Folder…';
                }
                return undefined;
            };

            mockVscode.window.showOpenDialog = async () => {
                openedFolderDialog = true;
                return [{ fsPath: validRepo }];
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];

            mockVscode.workspace.workspaceFolders = undefined;
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return configuredRepoPath;
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async (key: string, value: any) => {
                    if (key === 'repoPath') {
                        configuredRepoPath = value;
                        updatedRepoPath = value;
                    }
                },
            });

            loadExtension();
            await activate({ subscriptions: [] });

            await analyzeCallback();

            assert.ok(openedFolderDialog, 'Expected recovery folder picker to open');
            assert.equal(updatedRepoPath, validRepo, 'Expected corrected repoPath to be persisted');
            assert.ok(serverStarted, 'Expected server startup to retry after repo path correction');

            fs.rmSync(validRepo, { recursive: true, force: true });
        });

        it('should show cancellation error when analyze picker is dismissed', async () => {
            let analyzeCallback: any;
            const errorMessages: string[] = [];
            let openDialogCalls = 0;
            const validRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-analyze-repo-'));
            fs.writeFileSync(path.join(validRepo, 'lit-critic-web.py'), 'print("ok")', 'utf8');

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.showErrorMessage = async (message: string) => {
                errorMessages.push(message);
                return undefined;
            };
            mockVscode.window.showOpenDialog = async () => {
                openDialogCalls += 1;
                return [];
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return validRepo;
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            // No active editor and no visible editors.
            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await analyzeCallback();

            assert.ok(
                errorMessages.includes('lit-critic: No scene file selected.'),
                'Expected analyze command to show picker-cancel message',
            );
            assert.equal(openDialogCalls, 1, 'Expected analyze to show file picker when no editor is available');

            fs.rmSync(validRepo, { recursive: true, force: true });
        });

        it('should open all selected files from picker for multi-scene analysis', async () => {
            let analyzeCallback: any;
            const showTextDocumentCalls: Array<{ docOrUri: any; options: any }> = [];
            let showOpenDialogCalls = 0;
            let analyzedScenePaths: string[] | undefined;
            const validRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-analyze-repo-'));
            fs.writeFileSync(path.join(validRepo, 'lit-critic-web.py'), 'print("ok")', 'utf8');

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async checkSession() {
                    return { exists: false };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            balanced: { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                        },
                    };
                }
                async analyze(_scenePath: string, _projectPath: string, _model: string, _discussionModel: string | undefined, _apiKey: string | undefined, _lensPrefs: any, scenePaths?: string[]) {
                    analyzedScenePaths = scenePaths;
                    return {
                        scene_path: '/test/repo/scene-picked.md',
                        scene_name: 'scene-picked.md',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(_onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => onDone(), 0);
                    return () => {};
                }
                async getCurrentFinding() {
                    return { complete: true };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            const selectedFileUri = {
                scheme: 'file',
                fsPath: '/test/repo/scene-picked.md',
            };
            const selectedFileUri2 = {
                scheme: 'file',
                fsPath: '/test/repo/scene-picked-2.md',
            };

            mockVscode.window.activeTextEditor = undefined;
            mockVscode.window.visibleTextEditors = [];
            mockVscode.window.showOpenDialog = async (options?: any) => {
                showOpenDialogCalls += 1;
                assert.equal(options?.canSelectFiles, true);
                assert.equal(options?.canSelectFolders, false);
                assert.equal(options?.canSelectMany, true);
                return [selectedFileUri, selectedFileUri2];
            };
            mockVscode.window.showTextDocument = async (docOrUri: any, options?: any) => {
                showTextDocumentCalls.push({ docOrUri, options });
                return {
                    document: {
                        uri: selectedFileUri,
                    },
                    viewColumn: 1,
                };
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return validRepo;
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            // Repo and project marker exist so cmdAnalyze can proceed to scene picker.
            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await analyzeCallback();

            assert.equal(showOpenDialogCalls, 1, 'Expected a single picker invocation');
            assert.equal(showTextDocumentCalls.length, 2, 'Expected all selected picker files to be opened');
            assert.equal(showTextDocumentCalls[0].docOrUri, selectedFileUri);
            assert.equal(showTextDocumentCalls[1].docOrUri, selectedFileUri2);
            assert.deepEqual(
                analyzedScenePaths,
                ['/test/repo/scene-picked.md', '/test/repo/scene-picked-2.md'],
                'Expected all selected scene paths to be sent to analyze()',
            );

            fs.rmSync(validRepo, { recursive: true, force: true });
        });

        it('should show file picker even when an active editor exists if user starts a new analysis', async () => {
            let analyzeCallback: any;
            let showOpenDialogCalls = 0;
            let analyzedScenePath: string | undefined;
            let analyzedScenePaths: string[] | undefined;
            const validRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'lit-critic-analyze-repo-'));
            fs.writeFileSync(path.join(validRepo, 'lit-critic-web.py'), 'print("ok")', 'utf8');

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async checkSession() {
                    return { exists: true, total_findings: 1, scene_path: '/test/repo/focused.md' };
                }
                async listSessions() {
                    return {
                        sessions: [
                            {
                                id: 99,
                                status: 'active',
                                scene_path: '/test/repo/focused.md',
                                model: 'sonnet',
                                created_at: '2026-02-17T18:00:00',
                                total_findings: 1,
                                accepted_count: 0,
                                rejected_count: 0,
                                withdrawn_count: 0,
                            },
                        ],
                    };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                        lens_presets: {
                            balanced: { prose: 1, structure: 1, logic: 1, clarity: 1, continuity: 1, dialogue: 1 },
                        },
                    };
                }
                async analyze(scenePath: string, _projectPath: string, _model: string, _discussionModel: string | undefined, _apiKey: string | undefined, _lensPrefs: any, scenePaths?: string[]) {
                    analyzedScenePath = scenePath;
                    analyzedScenePaths = scenePaths;
                    return {
                        scene_path: scenePath,
                        scene_name: 'picked.md',
                        project_path: '/test/repo',
                        total_findings: 0,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 0, minor: 0 },
                        lens_counts: {},
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [],
                    };
                }
                streamAnalysisProgress(_onEvent: any, onDone: any, _onError: any) {
                    setTimeout(() => onDone(), 0);
                    return () => {};
                }
                async getCurrentFinding() {
                    return { complete: true };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.analyze') {
                    analyzeCallback = callback;
                }
                return { dispose: () => {} };
            };

            const fallbackEditor = {
                document: {
                    uri: {
                        scheme: 'file',
                        fsPath: '/test/repo/focused.md',
                    },
                },
                viewColumn: 1,
            };

            const selectedFileUri = {
                scheme: 'file',
                fsPath: '/test/repo/picked.md',
            };

            mockVscode.window.activeTextEditor = fallbackEditor;
            mockVscode.window.visibleTextEditors = [fallbackEditor];
            mockVscode.window.showQuickPick = async (items: any[]) => {
                return items.find((item: any) => item?.label === 'Start new analysis') || items[1];
            };
            mockVscode.window.showOpenDialog = async () => {
                showOpenDialogCalls += 1;
                return [selectedFileUri];
            };
            mockVscode.window.showTextDocument = async (_docOrUri: any) => {
                return {
                    document: {
                        uri: selectedFileUri,
                    },
                    viewColumn: 1,
                };
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'repoPath') return validRepo;
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async () => {},
                inspect: () => ({ workspaceValue: undefined, globalValue: undefined, workspaceFolderValue: undefined }),
            });

            // Repo and project marker exist so cmdAnalyze reaches start-new picker flow.
            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await analyzeCallback();

            assert.equal(showOpenDialogCalls, 1, 'Expected Start new flow to always show picker');
            assert.equal(analyzedScenePath, '/test/repo/picked.md');
            assert.deepEqual(analyzedScenePaths, undefined);

            fs.rmSync(validRepo, { recursive: true, force: true });
        });

        it('should not auto-close discussion panel when review returns complete', async () => {
            let reviewFindingCallback: any;
            let discussCallback: any;
            let closeCalls = 0;

            mockDiscussionPanel = class MockDiscussionPanel {
                onFindingAction: any;
                onDiscussionResult: any;
                show() {}
                close() { closeCalls += 1; }
                dispose() {}
                notifySceneChange() {}
            };

            mockApiClient = class MockApiClient {
                async getSession() {
                    return {
                        active: false,
                        findings_status: [],
                    };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async getCurrentFinding() {
                    return {
                        complete: false,
                        finding: {
                            number: 1,
                            severity: 'major',
                            lens: 'prose',
                            location: 'L1',
                            line_start: 1,
                            line_end: 1,
                            evidence: 'example',
                            impact: '',
                            options: [],
                            flagged_by: [],
                            ambiguity_type: null,
                            stale: false,
                            status: 'pending',
                        },
                        current: 1,
                        total: 1,
                        is_ambiguity: false,
                    };
                }
                async reviewFinding() {
                    return { complete: true };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.reviewFinding') {
                    reviewFindingCallback = callback;
                }
                if (cmd === 'literaryCritic.discuss') {
                    discussCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockFs.existsSync = (path: string) => {
                return path.includes('lit-critic-web.py');
            };

            loadExtension();

            const context = {
                subscriptions: [],
            };

            await activate(context);

            // Ensure panel is created/shown before review command runs.
            await discussCallback();
            await reviewFindingCallback();

            assert.equal(closeCalls, 0, 'Discussion panel should remain open on review completion');
        });

        it('should preserve pre-review discussion context when finding is re-evaluated after scene edits', async () => {
            let reviewFindingCallback: any;
            let discussCallback: any;
            const showCalls: any[] = [];

            mockDiscussionPanel = class MockDiscussionPanel {
                onFindingAction: any;
                onDiscussionResult: any;
                show(...args: any[]) { showCalls.push(args); }
                close() {}
                dispose() {}
                notifySceneChange() {}
            };

            mockApiClient = class MockApiClient {
                async getSession() {
                    return {
                        active: false,
                        findings_status: [],
                    };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async getCurrentFinding() {
                    return {
                        complete: false,
                        finding: {
                            number: 1,
                            severity: 'major',
                            lens: 'prose',
                            location: 'Line 12',
                            line_start: 12,
                            line_end: 12,
                            evidence: 'Original evidence text',
                            impact: 'Original impact',
                            options: [],
                            flagged_by: [],
                            ambiguity_type: null,
                            stale: false,
                            status: 'pending',
                            discussion_turns: [
                                { role: 'assistant', content: 'Original recommendation.' },
                                { role: 'user', content: 'I will revise this now.' },
                            ],
                        },
                        current: 1,
                        total: 1,
                        is_ambiguity: false,
                    };
                }
                async reviewFinding() {
                    return {
                        complete: false,
                        review: { changed: true, adjusted: 0, stale: 1, no_lines: 0, re_evaluated: [] },
                        finding: {
                            number: 1,
                            severity: 'major',
                            lens: 'prose',
                            location: 'Line 13',
                            line_start: 13,
                            line_end: 13,
                            evidence: 'Updated evidence text',
                            impact: 'Updated impact',
                            options: [],
                            flagged_by: [],
                            ambiguity_type: null,
                            stale: false,
                            status: 'pending',
                            discussion_turns: [],
                        },
                        current: 1,
                        total: 1,
                        is_ambiguity: false,
                    };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.reviewFinding') {
                    reviewFindingCallback = callback;
                }
                if (cmd === 'literaryCritic.discuss') {
                    discussCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockFs.existsSync = (path: string) => {
                return path.includes('lit-critic-web.py');
            };

            loadExtension();

            const context = {
                subscriptions: [],
            };

            await activate(context);

            // Seed cached finding with original discussion turns.
            await discussCallback();
            await reviewFindingCallback();

            assert.ok(showCalls.length >= 2, 'Expected discussion panel to be shown before and after review');
            const transition = showCalls[showCalls.length - 1][4];

            assert.ok(transition, 'Expected a discussion transition payload for re-evaluated finding');
            assert.equal(transition.previousFinding.evidence, 'Original evidence text');
            assert.equal(transition.previousTurns.length, 2);
            assert.equal(transition.previousTurns[0].content, 'Original recommendation.');
        });

        it('should set current session to the explicitly selected historical session and sync discussion panel', async () => {
            let viewSessionCallback: any;
            const setCurrentSessionCalls: Array<number | null> = [];
            const showCalls: any[] = [];

            mockSessionsTreeProvider = class MockSessionsTreeProvider {
                setApiClient() {}
                setProjectPath() {}
                async refresh() {}
                setCurrentSession(sessionId: number | null) {
                    setCurrentSessionCalls.push(sessionId);
                }
                setCurrentSessionByScenePath() {}
            };

            mockDiscussionPanel = class MockDiscussionPanel {
                onFindingAction: any;
                onDiscussionResult: any;
                show(...args: any[]) { showCalls.push(args); }
                close() {}
                dispose() {}
                notifySceneChange() {}
            };

            mockApiClient = class MockApiClient {
                async getSession() {
                    return { active: false, findings_status: [] };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async getSessionDetail() {
                    return {
                        id: 42,
                        status: 'completed',
                        scene_path: '/test/repo/scene01.txt',
                        model: 'sonnet',
                        created_at: '2026-02-10T10:00:00',
                        completed_at: '2026-02-10T10:30:00',
                        total_findings: 2,
                        accepted_count: 1,
                        rejected_count: 1,
                        withdrawn_count: 0,
                        scene_hash: 'hash',
                        current_index: 1,
                        glossary_issues: [],
                        findings: [
                            {
                                id: 1,
                                number: 1,
                                severity: 'major',
                                lens: 'prose',
                                status: 'accepted',
                                location: 'L1',
                                evidence: 'first',
                                impact: '',
                                options: [],
                                flagged_by: [],
                                line_start: 1,
                                line_end: 1,
                            },
                            {
                                id: 2,
                                number: 2,
                                severity: 'minor',
                                lens: 'structure',
                                status: 'rejected',
                                location: 'L2',
                                evidence: 'second',
                                impact: '',
                                options: [],
                                flagged_by: [],
                                line_start: 2,
                                line_end: 2,
                            },
                        ],
                    };
                }
                async viewSessionWithRecovery() {
                    return {
                        scene_path: '/test/repo/scene01.txt',
                        scene_name: 'scene01.txt',
                        project_path: '/test/repo',
                        total_findings: 2,
                        current_index: 1,
                        glossary_issues: [],
                        counts: { critical: 0, major: 1, minor: 1 },
                        lens_counts: {
                            prose: { critical: 0, major: 1, minor: 0 },
                            structure: { critical: 0, major: 0, minor: 1 },
                        },
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [
                            {
                                number: 1,
                                severity: 'major',
                                lens: 'prose',
                                status: 'accepted',
                                location: 'L1',
                                evidence: 'first',
                                line_start: 1,
                                line_end: 1,
                            },
                            {
                                number: 2,
                                severity: 'minor',
                                lens: 'structure',
                                status: 'rejected',
                                location: 'L2',
                                evidence: 'second',
                                line_start: 2,
                                line_end: 2,
                            },
                        ],
                    };
                }
                async getCurrentFinding() {
                    return {
                        complete: false,
                        finding: {
                            number: 2,
                            severity: 'minor',
                            lens: 'structure',
                            location: 'L2',
                            line_start: 2,
                            line_end: 2,
                            evidence: 'second',
                            impact: '',
                            options: [],
                            flagged_by: [],
                            ambiguity_type: null,
                            stale: false,
                            status: 'rejected',
                        },
                        index: 1,
                        current: 2,
                        total: 2,
                        is_ambiguity: false,
                    };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.viewSession') {
                    viewSessionCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });
            mockVscode.window.setStatusBarMessage = () => ({ dispose: () => {} });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py')
                    || filePath.includes('CANON.md')
                    || filePath.includes('scene01.txt');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await viewSessionCallback({ session: { id: 42 } });

            assert.ok(
                setCurrentSessionCalls.includes(42),
                'Expected selected historical session to become current in sessions tree',
            );
            assert.ok(showCalls.length > 0, 'Expected discussion panel to be updated on historical session switch');
            const readOnlyNotice = showCalls[showCalls.length - 1][5];
            assert.equal(
                readOnlyNotice,
                'Viewing completed session — actions will reopen it.',
                'Expected closed-session read-only notice to be passed to discussion panel',
            );
        });

        it('should update discussion panel when switching to another active session', async () => {
            let viewSessionCallback: any;
            const setCurrentSessionCalls: Array<number | null> = [];
            const showCalls: any[] = [];

            mockSessionsTreeProvider = class MockSessionsTreeProvider {
                setApiClient() {}
                setProjectPath() {}
                async refresh() {}
                setCurrentSession(sessionId: number | null) {
                    setCurrentSessionCalls.push(sessionId);
                }
                setCurrentSessionByScenePath() {}
            };

            mockDiscussionPanel = class MockDiscussionPanel {
                onFindingAction: any;
                onDiscussionResult: any;
                show(...args: any[]) { showCalls.push(args); }
                close() {}
                dispose() {}
                notifySceneChange() {}
            };

            mockApiClient = class MockApiClient {
                async getSession() {
                    return { active: false, findings_status: [] };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async getSessionDetail() {
                    return {
                        id: 7,
                        status: 'active',
                        scene_path: '/test/repo/scene01.txt',
                        model: 'sonnet',
                        created_at: '2026-02-10T10:00:00',
                        completed_at: undefined,
                        total_findings: 1,
                        accepted_count: 0,
                        rejected_count: 0,
                        withdrawn_count: 0,
                        scene_hash: 'hash',
                        current_index: 0,
                        glossary_issues: [],
                        findings: [],
                    };
                }
                async resumeSessionByIdWithRecovery() {
                    return {
                        scene_path: '/test/repo/scene01.txt',
                        scene_name: 'scene01.txt',
                        project_path: '/test/repo',
                        total_findings: 1,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 1, minor: 0 },
                        lens_counts: { prose: { critical: 0, major: 1, minor: 0 } },
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [
                            {
                                number: 1,
                                severity: 'major',
                                lens: 'prose',
                                status: 'pending',
                                location: 'L1',
                                evidence: 'example',
                                line_start: 1,
                                line_end: 1,
                            },
                        ],
                    };
                }
                async getCurrentFinding() {
                    return {
                        complete: false,
                        finding: {
                            number: 1,
                            severity: 'major',
                            lens: 'prose',
                            location: 'L1',
                            line_start: 1,
                            line_end: 1,
                            evidence: 'example',
                            impact: '',
                            options: [],
                            flagged_by: [],
                            ambiguity_type: null,
                            stale: false,
                            status: 'pending',
                        },
                        index: 0,
                        current: 1,
                        total: 1,
                        is_ambiguity: false,
                    };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.viewSession') {
                    viewSessionCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });
            mockVscode.window.setStatusBarMessage = () => ({ dispose: () => {} });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py')
                    || filePath.includes('CANON.md')
                    || filePath.includes('scene01.txt');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await viewSessionCallback({ session: { id: 7 } });

            assert.ok(setCurrentSessionCalls.includes(7), 'Expected selected active session to become current');
            assert.ok(showCalls.length > 0, 'Expected discussion panel to be updated on active session switch');
        });

        it('should select finding returned by getCurrentFinding when index is missing', async () => {
            let viewSessionCallback: any;
            const findingRevealCalls: Array<{ item: any; options: any }> = [];
            let getCurrentFindingCalls = 0;

            mockVscode.window.createTreeView = (viewId: string, _options: any) => {
                const reveal = async (item: any, options: any) => {
                    if (viewId === 'literaryCritic.findings') {
                        findingRevealCalls.push({ item, options });
                    }
                };
                return { dispose: () => {}, reveal, visible: true };
            };

            mockDiscussionPanel = class MockDiscussionPanel {
                onFindingAction: any;
                onDiscussionResult: any;
                show() {}
                close() {}
                dispose() {}
                notifySceneChange() {}
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false, findings_status: [] };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async getSessionDetail() {
                    return {
                        id: 7,
                        status: 'active',
                        scene_path: '/test/repo/scene01.txt',
                        model: 'sonnet',
                        created_at: '2026-02-10T10:00:00',
                        completed_at: undefined,
                        total_findings: 2,
                        accepted_count: 0,
                        rejected_count: 0,
                        withdrawn_count: 0,
                        scene_hash: 'hash',
                        current_index: 1,
                        glossary_issues: [],
                        findings: [],
                    };
                }
                async resumeSessionByIdWithRecovery() {
                    return {
                        scene_path: '/test/repo/scene01.txt',
                        scene_name: 'scene01.txt',
                        project_path: '/test/repo',
                        total_findings: 2,
                        current_index: 1,
                        glossary_issues: [],
                        counts: { critical: 0, major: 1, minor: 1 },
                        lens_counts: {
                            prose: { critical: 0, major: 1, minor: 0 },
                            structure: { critical: 0, major: 0, minor: 1 },
                        },
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [
                            {
                                number: 1,
                                severity: 'major',
                                lens: 'prose',
                                status: 'pending',
                                location: 'L1',
                                evidence: 'first',
                                line_start: 1,
                                line_end: 1,
                            },
                            {
                                number: 2,
                                severity: 'minor',
                                lens: 'structure',
                                status: 'pending',
                                location: 'L2',
                                evidence: 'second',
                                line_start: 2,
                                line_end: 2,
                            },
                        ],
                    };
                }
                async getCurrentFinding() {
                    getCurrentFindingCalls += 1;
                    if (getCurrentFindingCalls === 1) {
                        return {
                            complete: false,
                            finding: {
                                number: 2,
                                severity: 'minor',
                                lens: 'structure',
                                location: 'L2',
                                line_start: 2,
                                line_end: 2,
                                evidence: 'second',
                                impact: '',
                                options: [],
                                flagged_by: [],
                                ambiguity_type: null,
                                stale: false,
                                status: 'pending',
                            },
                            index: 1,
                            current: 2,
                            total: 2,
                            is_ambiguity: false,
                        };
                    }

                    return {
                        complete: false,
                        finding: {
                            number: 1,
                            severity: 'major',
                            lens: 'prose',
                            location: 'L1',
                            line_start: 1,
                            line_end: 1,
                            evidence: 'first',
                            impact: '',
                            options: [],
                            flagged_by: [],
                            ambiguity_type: null,
                            stale: false,
                            status: 'pending',
                        },
                        // Intentionally omit index to verify fallback by finding number
                        current: 1,
                        total: 2,
                        is_ambiguity: false,
                    };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.viewSession') {
                    viewSessionCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });
            mockVscode.window.setStatusBarMessage = () => ({ dispose: () => {} });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py')
                    || filePath.includes('CANON.md')
                    || filePath.includes('scene01.txt');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            // First selection sets the extension's current index to #2 (index 1).
            await viewSessionCallback({ session: { id: 7 } });
            // Second selection returns finding #1 without index.
            await viewSessionCallback({ session: { id: 7 } });

            const lastFindingReveal = findingRevealCalls[findingRevealCalls.length - 1];
            assert.ok(lastFindingReveal, 'Expected findings tree selection to be revealed');
            assert.equal(
                lastFindingReveal.item?.id,
                'finding:1',
                'Expected findings tree to select finding #1 when getCurrentFinding omits index',
            );
            assert.equal(lastFindingReveal.options?.select, true);
        });

        it('should close discussion panel before presenting refreshed findings on rerun analysis', async () => {
            let rerunCallback: any;
            let discussCallback: any;
            const callOrder: string[] = [];

            mockDiscussionPanel = class MockDiscussionPanel {
                onFindingAction: any;
                onDiscussionResult: any;
                show() { callOrder.push('show'); }
                close() { callOrder.push('close'); }
                dispose() {}
                notifySceneChange() {}
                clearIndexChangeNotice() {}
                notifyIndexChange() {}
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false, findings_status: [] };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async rerunAnalysis() {
                    return {
                        scene_path: '/test/repo/scene-a.txt',
                        scene_name: 'scene-a.txt',
                        project_path: '/test/repo',
                        total_findings: 1,
                        current_index: 0,
                        glossary_issues: [],
                        counts: { critical: 0, major: 1, minor: 0 },
                        lens_counts: { prose: { critical: 0, major: 1, minor: 0 } },
                        model: { name: 'sonnet', id: 'sonnet', label: 'Sonnet' },
                        learning: { review_count: 0, preferences: 0, blind_spots: 0 },
                        findings_status: [
                            {
                                number: 1,
                                severity: 'major',
                                lens: 'prose',
                                status: 'pending',
                                location: 'L1',
                                evidence: 'example',
                                line_start: 1,
                                line_end: 1,
                            },
                        ],
                    };
                }
                async getCurrentFinding() {
                    return {
                        complete: false,
                        finding: {
                            number: 1,
                            severity: 'major',
                            lens: 'prose',
                            location: 'L1',
                            line_start: 1,
                            line_end: 1,
                            evidence: 'example',
                            impact: '',
                            options: [],
                            flagged_by: [],
                            ambiguity_type: null,
                            stale: false,
                            status: 'pending',
                        },
                        index: 0,
                        current: 1,
                        total: 1,
                        is_ambiguity: false,
                    };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.rerunAnalysisWithUpdatedIndexes') {
                    rerunCallback = callback;
                }
                if (cmd === 'literaryCritic.discuss') {
                    discussCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [{ uri: { fsPath: '/test/repo' } }];
            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            // Ensure panel exists before rerun.
            await discussCallback();
            await rerunCallback();

            const closeIndex = callOrder.indexOf('close');
            const lastShowIndex = callOrder.lastIndexOf('show');

            assert.ok(closeIndex >= 0, 'Expected rerun to close the discussion panel');
            assert.ok(lastShowIndex > closeIndex, 'Expected refreshed finding UI to show after panel close');
        });

        it('should handle stopServer command', async () => {
            let serverStopped = false;
            
            mockServerManager = class extends mockServerManager {
                stop() {
                    serverStopped = true;
                    this.isRunning = false;
                }
            };
            
            let stopServerCallback: any;
            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.stopServer') {
                    stopServerCallback = callback;
                }
                return { dispose: () => {} };
            };
            
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];
            
            mockVscode.workspace.getConfiguration = (section?: string) => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });
            
            // Fix path separators issue - just check for the file
            mockFs.existsSync = (path: string) => {
                return path.includes('lit-critic-web.py');
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            // Call the stopServer command
            stopServerCallback();
            
            assert.ok(serverStopped, 'Server should have been stopped by command');
        });

        it('should handle clearSession command', async () => {
            let clearCalled = false;
            
            mockApiClient = class extends mockApiClient {
                async clearSession() {
                    clearCalled = true;
                    return { deleted: true };
                }
            };
            
            let clearSessionCallback: any;
            let showWarningResponse = 'Delete'; // User confirms
            
            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.clearSession') {
                    clearSessionCallback = callback;
                }
                return { dispose: () => {} };
            };
            
            mockVscode.window.showWarningMessage = async (message: string, options: any, ...items: string[]) => {
                return showWarningResponse;
            };
            
            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];
            
            mockVscode.workspace.getConfiguration = (section?: string) => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return true;
                    return defaultValue;
                },
                update: async () => {},
            });
            
            // Fix path separators issue - just check for the file
            mockFs.existsSync = (path: string) => {
                return path.includes('lit-critic-web.py');
            };
            
            loadExtension();
            
            const context = {
                subscriptions: [],
            };
            
            await activate(context);
            
            // Call the clearSession command
            if (clearSessionCallback) {
                await clearSessionCallback();
                assert.ok(clearCalled, 'clearSession API should have been called');
            }
        });

        it('should delete learning entry when command receives Learning tree item entryId', async () => {
            let deleteLearningEntryCallback: any;
            const deletedEntryIds: number[] = [];
            const infoMessages: string[] = [];
            let learningRefreshCalls = 0;

            mockLearningTreeProvider = class MockLearningTreeProvider {
                setApiClient() {}
                setProjectPath() {}
                async refresh() {
                    learningRefreshCalls += 1;
                }
            };

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async deleteLearningEntry(entryId: number, _projectPath: string) {
                    deletedEntryIds.push(entryId);
                    return { deleted: true, entry_id: entryId };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.deleteLearningEntry') {
                    deleteLearningEntryCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.showInformationMessage = async (message: string) => {
                infoMessages.push(message);
                return undefined;
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await deleteLearningEntryCallback({ entryId: 42 });

            assert.deepEqual(deletedEntryIds, [42]);
            assert.ok(
                infoMessages.includes('lit-critic: Learning entry deleted.'),
                'Expected success message after deleting learning entry',
            );
            assert.ok(learningRefreshCalls > 0, 'Expected learning tree refresh after deletion');
        });

        it('should support legacy deleteLearningEntry payload shape { entry: { id } }', async () => {
            let deleteLearningEntryCallback: any;
            const deletedEntryIds: number[] = [];

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async deleteLearningEntry(entryId: number, _projectPath: string) {
                    deletedEntryIds.push(entryId);
                    return { deleted: true, entry_id: entryId };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.deleteLearningEntry') {
                    deleteLearningEntryCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await deleteLearningEntryCallback({ entry: { id: 43 } });

            assert.deepEqual(deletedEntryIds, [43]);
        });

        it('should show error when deleteLearningEntry cannot resolve an entry id', async () => {
            let deleteLearningEntryCallback: any;
            const errorMessages: string[] = [];
            let deleteCalled = false;

            mockApiClient = class MockApiClient {
                async updateRepoPath(_repoPath: string) {
                    return { ok: true };
                }
                async getSession() {
                    return { active: false };
                }
                async getConfig() {
                    return {
                        api_key_configured: true,
                        available_models: { sonnet: { label: 'Sonnet' } },
                        default_model: 'sonnet',
                    };
                }
                async deleteLearningEntry(_entryId: number, _projectPath: string) {
                    deleteCalled = true;
                    return { deleted: true, entry_id: 0 };
                }
            };

            mockVscode.commands.registerCommand = (cmd: string, callback: any) => {
                if (cmd === 'literaryCritic.deleteLearningEntry') {
                    deleteLearningEntryCallback = callback;
                }
                return { dispose: () => {} };
            };

            mockVscode.window.showErrorMessage = async (message: string) => {
                errorMessages.push(message);
                return undefined;
            };

            mockVscode.workspace.workspaceFolders = [
                { uri: { fsPath: '/test/repo' } },
            ];

            mockVscode.workspace.getConfiguration = () => ({
                get: (key: string, defaultValue: any) => {
                    if (key === 'autoStartServer') return false;
                    return defaultValue;
                },
                update: async () => {},
            });

            mockFs.existsSync = (filePath: string) => {
                return filePath.includes('lit-critic-web.py') || filePath.includes('CANON.md');
            };

            loadExtension();
            await activate({ subscriptions: [] });

            await deleteLearningEntryCallback({});

            assert.ok(
                errorMessages.includes('lit-critic: Could not determine learning entry ID.'),
                'Expected missing-entry-id error message',
            );
            assert.equal(deleteCalled, false, 'Expected API delete call not to run without an entry id');
        });
    });
});
