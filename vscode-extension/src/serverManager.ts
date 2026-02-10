/**
 * Server Manager — spawns and manages the FastAPI backend process.
 *
 * Lifecycle:
 *   1. On activation, spawn `python lit-critic-web.py --port <port>`
 *   2. Health-check loop until the server responds
 *   3. On deactivation (or stop command), kill the process
 */

import * as vscode from 'vscode';
import { ChildProcess, spawn } from 'child_process';
import * as path from 'path';
import * as http from 'http';

export class ServerManager implements vscode.Disposable {
    private process: ChildProcess | null = null;
    private outputChannel: vscode.OutputChannel;
    private _isRunning = false;
    private _port: number;
    private _repoRoot: string;

    /** Fired when the server becomes ready (health check passed). */
    readonly onReady: vscode.Event<void>;
    private _onReadyEmitter = new vscode.EventEmitter<void>();

    /** Fired when the server stops (process exit or kill). */
    readonly onStopped: vscode.Event<void>;
    private _onStoppedEmitter = new vscode.EventEmitter<void>();

    constructor(repoRoot: string) {
        this._repoRoot = repoRoot;
        this.outputChannel = vscode.window.createOutputChannel('lit-critic Server');
        this.onReady = this._onReadyEmitter.event;
        this.onStopped = this._onStoppedEmitter.event;

        const config = vscode.workspace.getConfiguration('literaryCritic');
        this._port = config.get<number>('serverPort', 8000);
    }

    get isRunning(): boolean {
        return this._isRunning;
    }

    get port(): number {
        return this._port;
    }

    get baseUrl(): string {
        return `http://127.0.0.1:${this._port}`;
    }

    /**
     * Start the backend server. Resolves when the health check passes.
     * If the server is already running (externally or from a prior start), reuses it.
     */
    async start(): Promise<void> {
        // Check if something is already listening on the port
        if (await this.healthCheck()) {
            this._isRunning = true;
            this.outputChannel.appendLine(`Server already running on port ${this._port}`);
            this._onReadyEmitter.fire();
            return;
        }

        const config = vscode.workspace.getConfiguration('literaryCritic');
        const pythonPath = config.get<string>('pythonPath', 'python');
        this._port = config.get<number>('serverPort', 8000);

        const scriptPath = path.join(this._repoRoot, 'lit-critic-web.py');

        this.outputChannel.appendLine(`Starting server: ${pythonPath} ${scriptPath} --port ${this._port}`);
        this.outputChannel.show(true);

        this.process = spawn(pythonPath, [scriptPath, '--port', String(this._port)], {
            cwd: this._repoRoot,
            env: { ...process.env },
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        this.process.stdout?.on('data', (data: Buffer) => {
            this.outputChannel.appendLine(data.toString().trimEnd());
        });

        this.process.stderr?.on('data', (data: Buffer) => {
            this.outputChannel.appendLine(data.toString().trimEnd());
        });

        this.process.on('error', (err) => {
            this.outputChannel.appendLine(`Server process error: ${err.message}`);
            this._isRunning = false;
            this._onStoppedEmitter.fire();
        });

        this.process.on('exit', (code, signal) => {
            this.outputChannel.appendLine(
                `Server process exited (code=${code}, signal=${signal})`
            );
            this._isRunning = false;
            this.process = null;
            this._onStoppedEmitter.fire();
        });

        // Wait for the server to become ready
        await this.waitForReady();
    }

    /**
     * Stop the backend server.
     */
    stop(): void {
        if (this.process) {
            this.outputChannel.appendLine('Stopping server...');
            this.process.kill('SIGTERM');
            // Force kill after 5 seconds
            setTimeout(() => {
                if (this.process) {
                    this.process.kill('SIGKILL');
                    this.process = null;
                }
            }, 5000);
        }
        this._isRunning = false;
    }

    dispose(): void {
        this.stop();
        this._onReadyEmitter.dispose();
        this._onStoppedEmitter.dispose();
        this.outputChannel.dispose();
    }

    /**
     * Single health check — GET /api/config.
     */
    private healthCheck(): Promise<boolean> {
        return new Promise((resolve) => {
            const req = http.get(`${this.baseUrl}/api/config`, { timeout: 2000 }, (res) => {
                resolve(res.statusCode === 200);
            });
            req.on('error', () => resolve(false));
            req.on('timeout', () => {
                req.destroy();
                resolve(false);
            });
        });
    }

    /**
     * Poll until the server is ready, or timeout.
     */
    private async waitForReady(timeoutMs = 30000, intervalMs = 500): Promise<void> {
        const start = Date.now();

        while (Date.now() - start < timeoutMs) {
            if (await this.healthCheck()) {
                this._isRunning = true;
                this.outputChannel.appendLine('Server is ready.');
                this._onReadyEmitter.fire();
                return;
            }

            // Check if process died
            if (this.process?.exitCode !== null && this.process?.exitCode !== undefined) {
                throw new Error(
                    `Server process exited with code ${this.process.exitCode} before becoming ready.`
                );
            }

            await new Promise((r) => setTimeout(r, intervalMs));
        }

        throw new Error(`Server did not become ready within ${timeoutMs / 1000}s.`);
    }
}
