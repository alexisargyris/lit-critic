import { strict as assert } from 'assert';
import { createFreshMockVscode } from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

describe('OperationTracker', () => {
    it('should not show status/progress UI for fast operations', async () => {
        const lines: string[] = [];
        let statusCalls = 0;
        let progressCalls = 0;
        const mockVscode = createFreshMockVscode();

        const { OperationTracker } = proxyquire('../../vscode-extension/src/operationTracker', {
            vscode: mockVscode,
        });

        const tracker = new OperationTracker({
            outputChannel: {
                appendLine: (line: string) => lines.push(line),
                show: () => {},
                dispose: () => {},
            } as any,
            slowThresholdMs: 50,
            progressThresholdMs: 100,
            setStatusBarMessage: ((_: string) => {
                statusCalls += 1;
                return { dispose: () => {} };
            }) as any,
            withProgress: (async () => {
                progressCalls += 1;
            }) as any,
        });

        const result = await tracker.run(
            { id: 'fast-op', title: 'Fast operation' },
            async () => 'ok',
        );

        assert.equal(result, 'ok');
        assert.equal(statusCalls, 0);
        assert.equal(progressCalls, 0);
        assert.ok(lines.some((line) => line.includes('OK fast-op')));

        tracker.dispose();
    });

    it('should show status bar feedback for slow operations', async () => {
        let statusCalls = 0;
        let statusDisposed = 0;
        let progressCalls = 0;
        const mockVscode = createFreshMockVscode();

        const { OperationTracker } = proxyquire('../../vscode-extension/src/operationTracker', {
            vscode: mockVscode,
        });

        const tracker = new OperationTracker({
            outputChannel: {
                appendLine: () => {},
                show: () => {},
                dispose: () => {},
            } as any,
            setStatusBarMessage: ((_: string) => {
                statusCalls += 1;
                return {
                    dispose: () => {
                        statusDisposed += 1;
                    },
                };
            }) as any,
            withProgress: (async () => {
                progressCalls += 1;
            }) as any,
        });

        await tracker.run(
            {
                id: 'slow-op',
                title: 'Slow operation',
                slowThresholdMs: 1,
                progressThresholdMs: 100,
            },
            async () => {
                await delay(20);
            },
        );

        assert.equal(statusCalls, 1);
        assert.equal(statusDisposed, 1);
        assert.equal(progressCalls, 0);

        tracker.dispose();
    });

    it('should show progress notification for very slow operations', async () => {
        let progressCalls = 0;
        let progressResolved = 0;
        const mockVscode = createFreshMockVscode();

        const { OperationTracker } = proxyquire('../../vscode-extension/src/operationTracker', {
            vscode: mockVscode,
        });

        const tracker = new OperationTracker({
            outputChannel: {
                appendLine: () => {},
                show: () => {},
                dispose: () => {},
            } as any,
            setStatusBarMessage: ((_: string) => ({ dispose: () => {} })) as any,
            withProgress: (async (_options: any, task: any) => {
                progressCalls += 1;
                await task(
                    { report: () => {} },
                    {
                        isCancellationRequested: false,
                        onCancellationRequested: () => ({ dispose: () => {} }),
                    },
                );
                progressResolved += 1;
            }) as any,
        });

        await tracker.run(
            {
                id: 'very-slow-op',
                title: 'Very slow operation',
                slowThresholdMs: 1,
                progressThresholdMs: 5,
            },
            async () => {
                await delay(25);
            },
        );

        assert.equal(progressCalls, 1);
        assert.equal(progressResolved, 1);

        tracker.dispose();
    });

    it('should log and rethrow operation errors', async () => {
        const lines: string[] = [];
        const mockVscode = createFreshMockVscode();

        const { OperationTracker } = proxyquire('../../vscode-extension/src/operationTracker', {
            vscode: mockVscode,
        });

        const tracker = new OperationTracker({
            outputChannel: {
                appendLine: (line: string) => lines.push(line),
                show: () => {},
                dispose: () => {},
            } as any,
            slowThresholdMs: 1,
            progressThresholdMs: 5,
            setStatusBarMessage: ((_: string) => ({ dispose: () => {} })) as any,
            withProgress: (async (_options: any, task: any) => {
                await task(
                    { report: () => {} },
                    {
                        isCancellationRequested: false,
                        onCancellationRequested: () => ({ dispose: () => {} }),
                    },
                );
            }) as any,
        });

        await assert.rejects(
            () => tracker.run(
                { id: 'failing-op', title: 'Failing operation' },
                async () => {
                    await delay(10);
                    throw new Error('boom');
                },
            ),
            /boom/,
        );

        assert.ok(lines.some((line) => line.includes('ERROR failing-op')));
        assert.ok(lines.some((line) => line.includes('boom')));

        tracker.dispose();
    });
});
