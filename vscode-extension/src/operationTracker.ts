import * as vscode from 'vscode';

export interface OperationProfile {
    id: string;
    title: string;
    statusMessage?: string;
    slowThresholdMs?: number;
    progressThresholdMs?: number;
    progressLocation?: vscode.ProgressLocation;
    cancellable?: boolean;
}

interface OperationTrackerOptions {
    outputChannel?: vscode.OutputChannel;
    slowThresholdMs?: number;
    progressThresholdMs?: number;
    verySlowThresholdMs?: number;
    now?: () => number;
    setStatusBarMessage?: typeof vscode.window.setStatusBarMessage;
    withProgress?: typeof vscode.window.withProgress;
}

/**
 * Lightweight wrapper for timing async operations and surfacing user feedback
 * only when an operation is actually taking noticeable time.
 */
export class OperationTracker implements vscode.Disposable {
    private readonly output: vscode.OutputChannel;
    private readonly defaultSlowThresholdMs: number;
    private readonly defaultProgressThresholdMs: number;
    private readonly verySlowThresholdMs: number;
    private readonly now: () => number;
    private readonly setStatusBarMessage: typeof vscode.window.setStatusBarMessage;
    private readonly withProgress: typeof vscode.window.withProgress;

    constructor(options: OperationTrackerOptions = {}) {
        this.output = options.outputChannel || vscode.window.createOutputChannel('lit-critic');
        this.defaultSlowThresholdMs = options.slowThresholdMs ?? 400;
        this.defaultProgressThresholdMs = options.progressThresholdMs ?? 1500;
        this.verySlowThresholdMs = options.verySlowThresholdMs ?? 5000;
        this.now = options.now || (() => Date.now());
        this.setStatusBarMessage = options.setStatusBarMessage || vscode.window.setStatusBarMessage.bind(vscode.window);
        this.withProgress = options.withProgress || vscode.window.withProgress.bind(vscode.window);
    }

    async run<T>(profile: OperationProfile, operation: () => Promise<T>): Promise<T> {
        const slowThresholdMs = profile.slowThresholdMs ?? this.defaultSlowThresholdMs;
        const progressThresholdMs = Math.max(
            profile.progressThresholdMs ?? this.defaultProgressThresholdMs,
            slowThresholdMs,
        );
        const start = this.now();

        let statusMessageDisposable: vscode.Disposable | undefined;
        let progressPromise: Thenable<void> | undefined;
        let resolveProgress: (() => void) | undefined;

        const slowTimer = setTimeout(() => {
            statusMessageDisposable = this.setStatusBarMessage(
                `$(sync~spin) lit-critic: ${profile.statusMessage || profile.title}`,
            );
        }, slowThresholdMs);

        const progressTimer = setTimeout(() => {
            progressPromise = this.withProgress(
                {
                    location: profile.progressLocation ?? vscode.ProgressLocation.Notification,
                    title: `lit-critic: ${profile.title}`,
                    cancellable: profile.cancellable ?? false,
                },
                async () => new Promise<void>((resolve) => {
                    resolveProgress = resolve;
                }),
            );
        }, progressThresholdMs);

        const completeUi = async (): Promise<void> => {
            clearTimeout(slowTimer);
            clearTimeout(progressTimer);

            statusMessageDisposable?.dispose();
            statusMessageDisposable = undefined;

            if (resolveProgress) {
                resolveProgress();
                resolveProgress = undefined;
            }
            if (progressPromise) {
                await Promise.resolve(progressPromise).catch(() => {
                    // Best effort cleanup only.
                });
                progressPromise = undefined;
            }
        };

        try {
            const result = await operation();
            await completeUi();

            const durationMs = this.now() - start;
            this.log('ok', profile.id, profile.title, durationMs, durationMs >= this.verySlowThresholdMs ? 'very-slow' : undefined);
            return result;
        } catch (error) {
            await completeUi();

            const durationMs = this.now() - start;
            const message = error instanceof Error ? error.message : String(error);
            this.log('error', profile.id, profile.title, durationMs, message);
            throw error;
        }
    }

    dispose(): void {
        this.output.dispose();
    }

    private log(status: 'ok' | 'error', id: string, title: string, durationMs: number, detail?: string): void {
        const duration = Math.round(durationMs);
        const marker = status === 'error'
            ? 'ERROR'
            : duration >= this.defaultProgressThresholdMs
                ? 'SLOW'
                : 'OK';

        const suffix = detail ? ` · ${detail}` : '';
        this.output.appendLine(
            `[${new Date().toISOString()}] ${marker} ${id} (${title}) in ${duration}ms${suffix}`,
        );
    }
}
