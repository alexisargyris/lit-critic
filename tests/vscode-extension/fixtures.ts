/**
 * Shared test fixtures and mocks for VS Code extension tests.
 * 
 * Provides mock implementations of:
 * - VS Code API objects
 * - HTTP responses
 * - Sample data (findings, sessions, etc.)
 */

import { EventEmitter } from 'events';

// ---------------------------------------------------------------------------
// Sample Data
// ---------------------------------------------------------------------------

export const sampleFinding = {
    number: 1,
    severity: 'major' as const,
    lens: 'prose',
    location: 'Paragraph 3',
    line_start: 42,
    line_end: 45,
    evidence: 'The rhythm breaks here with an awkward sentence structure.',
    impact: 'Disrupts reading flow and weakens tension.',
    options: [
        'Rewrite for smoother rhythm',
        'Break into two shorter sentences',
    ],
    flagged_by: ['prose'],
    ambiguity_type: null,
    stale: false,
    status: 'pending',
};

export const sampleFindings = [
    sampleFinding,
    {
        number: 2,
        severity: 'critical' as const,
        lens: 'structure',
        location: 'Scene opening',
        line_start: 1,
        line_end: 10,
        evidence: 'Scene lacks clear goal.',
        impact: 'Reader confusion about purpose.',
        options: ['Establish clear scene goal'],
        flagged_by: ['structure'],
        ambiguity_type: null,
        stale: false,
        status: 'pending',
    },
    {
        number: 3,
        severity: 'minor' as const,
        lens: 'prose',
        location: 'Paragraph 8',
        line_start: 78,
        line_end: 78,
        evidence: 'Passive voice: "was seen"',
        impact: 'Minor weakening of prose.',
        options: ['Use active voice'],
        flagged_by: ['prose'],
        ambiguity_type: null,
        stale: false,
        status: 'accepted',
    },
];

export const sampleAnalysisSummary = {
    scene_path: '/test/project/scene01.txt',
    scene_name: 'scene01.txt',
    project_path: '/test/project',
    total_findings: 3,
    current_index: 0,
    skip_minor: false,
    glossary_issues: [],
    counts: { critical: 1, major: 1, minor: 1 },
    lens_counts: {
        prose: { critical: 0, major: 1, minor: 1 },
        structure: { critical: 1, major: 0, minor: 0 },
    },
    model: { name: 'sonnet', id: 'claude-sonnet-4-20250514', label: 'Sonnet 4.5' },
    learning: { review_count: 0, preferences: 0, blind_spots: 0 },
};

export const sampleFindingResponse = {
    complete: false,
    finding: sampleFinding,
    index: 0,
    current: 1,
    total: 3,
    is_ambiguity: false,
};

export const sampleAdvanceResponse = {
    complete: false,
    finding: sampleFinding,
    index: 0,
    current: 1,
    total: 3,
    is_ambiguity: false,
    scene_change: null,
};

export const sampleSessionInfo = {
    active: true,
    scene_path: '/test/project/scene01.txt',
    scene_name: 'scene01.txt',
    project_path: '/test/project',
    total_findings: 3,
    current_index: 0,
    findings_status: sampleFindings.map(f => ({
        number: f.number,
        severity: f.severity,
        lens: f.lens,
        status: f.status,
        location: f.location,
        evidence: f.evidence,
        line_start: f.line_start,
        line_end: f.line_end,
    })),
};

export const sampleServerConfig = {
    api_key_configured: true,
    available_models: {
        'opus': { label: 'Opus 4.6 (deepest analysis)' },
        'sonnet': { label: 'Sonnet 4.5 (balanced, default)' },
        'haiku': { label: 'Haiku 4.5 (fast & cheap)' },
    },
    default_model: 'sonnet',
};

// ---------------------------------------------------------------------------
// Mock VS Code API
// ---------------------------------------------------------------------------

export class MockDiagnosticCollection {
    private diagnostics = new Map<string, any[]>();

    set(uri: any, diagnostics: any[]): void {
        this.diagnostics.set(uri.toString(), diagnostics);
    }

    get(uri: any): any[] | undefined {
        return this.diagnostics.get(uri.toString());
    }

    clear(): void {
        this.diagnostics.clear();
    }

    dispose(): void {
        this.clear();
    }

    // Test helper
    _getDiagnostics() {
        return this.diagnostics;
    }
}

export class MockStatusBarItem {
    text: string = '';
    tooltip: string = '';
    command: string | undefined = undefined;
    visible: boolean = false;

    show(): void {
        this.visible = true;
    }

    hide(): void {
        this.visible = false;
    }

    dispose(): void {
        this.visible = false;
    }
}

export class MockTreeItem {
    label: string;
    collapsibleState: number;
    description?: string;
    tooltip?: any;
    iconPath?: any;
    command?: any;
    contextValue?: string;

    constructor(label: string, collapsibleState: number = 0) {
        this.label = label;
        this.collapsibleState = collapsibleState;
    }
}

export class MockEventEmitter<T> {
    private listeners: Array<(e: T) => void> = [];

    get event() {
        return (listener: (e: T) => void) => {
            this.listeners.push(listener);
            return {
                dispose: () => {
                    const idx = this.listeners.indexOf(listener);
                    if (idx >= 0) this.listeners.splice(idx, 1);
                },
            };
        };
    }

    fire(data: T): void {
        for (const listener of this.listeners) {
            listener(data);
        }
    }

    dispose(): void {
        this.listeners = [];
    }
}

export const mockVscode = {
    languages: {
        createDiagnosticCollection: (name: string) => new MockDiagnosticCollection(),
    },
    window: {
        createStatusBarItem: (alignment: number, priority: number) => new MockStatusBarItem(),
        createTreeView: (viewId: string, options: any) => ({
            dispose: () => {},
            visible: true,
        }),
        showInformationMessage: async (message: string, ...items: string[]) => items[0],
        showWarningMessage: async (message: string, ...items: string[]) => items[0],
        showErrorMessage: async (message: string, ...items: string[]) => items[0],
        showQuickPick: async (items: any[], options?: any) => items[0],
        showInputBox: async (options?: any) => 'test input',
        createOutputChannel: (name: string) => ({
            appendLine: (text: string) => {},
            show: (preserveFocus?: boolean) => {},
            dispose: () => {},
        }),
        createWebviewPanel: (viewType: string, title: string, showOptions: any, options: any) => ({
            webview: {
                html: '',
                onDidReceiveMessage: (handler: any) => ({ dispose: () => {} }),
                postMessage: (msg: any) => {},
            },
            onDidDispose: (handler: any) => ({ dispose: () => {} }),
            reveal: (viewColumn?: number, preserveFocus?: boolean) => {},
            dispose: () => {},
            visible: true,
            viewColumn: 2,
        }),
        activeTextEditor: undefined,
        visibleTextEditors: [],
        showTextDocument: async (uri: any, options?: any) => ({}),
    },
    workspace: {
        getConfiguration: (section?: string) => ({
            get: (key: string, defaultValue?: any) => defaultValue,
            update: async (key: string, value: any, target?: any) => {},
        }),
        workspaceFolders: undefined,
    },
    commands: {
        registerCommand: (command: string, callback: (...args: any[]) => any) => ({
            dispose: () => {},
        }),
        executeCommand: async (command: string, ...rest: any[]) => {},
    },
    Uri: {
        file: (path: string) => ({ fsPath: path, toString: () => path }),
    },
    Range: class {
        start: any;
        end: any;
        constructor(start: any, end: any) {
            this.start = start;
            this.end = end;
        }
    },
    Position: class {
        line: number;
        character: number;
        constructor(line: number, character: number) {
            this.line = line;
            this.character = character;
        }
    },
    Diagnostic: class {
        range: any;
        message: string;
        severity: number;
        source?: string;
        code?: any;
        tags?: any[];
        constructor(range: any, message: string, severity: number) {
            this.range = range;
            this.message = message;
            this.severity = severity;
        }
    },
    DiagnosticSeverity: {
        Error: 0,
        Warning: 1,
        Information: 2,
        Hint: 3,
    },
    DiagnosticTag: {
        Unnecessary: 1,
        Deprecated: 2,
    },
    TreeItemCollapsibleState: {
        None: 0,
        Collapsed: 1,
        Expanded: 2,
    },
    ViewColumn: {
        One: 1,
        Two: 2,
        Beside: -2,
    },
    StatusBarAlignment: {
        Left: 1,
        Right: 2,
    },
    ThemeIcon: class {
        id: string;
        color?: any;
        constructor(id: string, color?: any) {
            this.id = id;
            this.color = color;
        }
    },
    ThemeColor: class {
        id: string;
        constructor(id: string) {
            this.id = id;
        }
    },
    MarkdownString: class {
        value: string = '';
        appendMarkdown(text: string): void {
            this.value += text;
        }
    },
    ConfigurationTarget: {
        Global: 1,
        Workspace: 2,
        WorkspaceFolder: 3,
    },
    EventEmitter: MockEventEmitter,
};

// ---------------------------------------------------------------------------
// Mock HTTP Responses
// ---------------------------------------------------------------------------

export class MockHttpResponse extends EventEmitter {
    statusCode: number;
    private body: string;

    constructor(statusCode: number, body: any) {
        super();
        this.statusCode = statusCode;
        this.body = typeof body === 'string' ? body : JSON.stringify(body);
    }

    simulateResponse(): void {
        setImmediate(() => {
            this.emit('data', Buffer.from(this.body));
            this.emit('end');
        });
    }
}

export class MockHttpRequest extends EventEmitter {
    private response: MockHttpResponse | null = null;
    private shouldError = false;
    private shouldTimeout = false;

    constructor(response?: MockHttpResponse, shouldError = false, shouldTimeout = false) {
        super();
        this.response = response || null;
        this.shouldError = shouldError;
        this.shouldTimeout = shouldTimeout;
    }

    write(data: any): void {
        // No-op
    }

    end(): void {
        setImmediate(() => {
            if (this.shouldError) {
                this.emit('error', new Error('Network error'));
            } else if (this.shouldTimeout) {
                this.emit('timeout');
            } else if (this.response) {
                this.emit('response', this.response);
                this.response.simulateResponse();
            }
        });
    }

    destroy(): void {
        this.removeAllListeners();
    }
}

export function createMockHttpModule(response?: MockHttpResponse, shouldError = false, shouldTimeout = false) {
    return {
        request: (options: any, callback?: any) => {
            const req = new MockHttpRequest(response, shouldError, shouldTimeout);
            if (callback) {
                req.on('response', callback);
            }
            return req;
        },
        get: (url: string | URL, options: any, callback?: any) => {
            const req = new MockHttpRequest(response, shouldError, shouldTimeout);
            if (typeof options === 'function') {
                callback = options;
            }
            if (callback) {
                req.on('response', callback);
            }
            // Auto-end for GET requests
            setImmediate(() => req.end());
            return req;
        },
    };
}

// ---------------------------------------------------------------------------
// Mock Child Process
// ---------------------------------------------------------------------------

export class MockChildProcess extends EventEmitter {
    exitCode: number | null = null;
    stdout: EventEmitter = new EventEmitter();
    stderr: EventEmitter = new EventEmitter();

    kill(signal?: string): void {
        this.exitCode = 0;
        this.emit('exit', 0, signal);
    }

    simulateSuccess(output = 'Server started'): void {
        setImmediate(() => {
            this.stdout.emit('data', Buffer.from(output));
        });
    }

    simulateError(error = 'Server error'): void {
        setImmediate(() => {
            this.stderr.emit('data', Buffer.from(error));
            this.exitCode = 1;
            this.emit('exit', 1, null);
        });
    }
}

export function createMockSpawn(process: MockChildProcess) {
    return (command: string, args: string[], options: any) => {
        return process;
    };
}
