/**
 * registerCommands — centralises all command-to-handler mappings.
 *
 * Keeping command IDs and their handlers in one place makes it easy to:
 *   - enumerate expected command IDs in tests,
 *   - add new commands without touching the activation entry point,
 *   - avoid business logic in the registration site.
 */

import * as vscode from 'vscode';

// ---------------------------------------------------------------------------
// Type for the handler map passed in by the caller
// ---------------------------------------------------------------------------

export interface CommandHandlers {
    cmdAnalyze: () => Promise<void>;
    cmdResume: () => Promise<void>;
    cmdNextFinding: () => Promise<void>;
    cmdAcceptFinding: () => Promise<void>;
    cmdRejectFinding: () => Promise<void>;
    cmdDiscuss: () => Promise<void>;
    cmdSelectFinding: (index: number) => Promise<void>;
    cmdReviewFinding: () => Promise<void>;
    cmdClearSession: () => Promise<void>;
    cmdRerunAnalysis: () => Promise<void>;
    cmdSelectModel: () => Promise<void>;
    cmdStopServer: () => void;
    cmdRefreshSessions: () => Promise<void>;
    cmdViewSession: (item: any) => Promise<void>;
    cmdDeleteSession: (item?: any) => Promise<void>;
    cmdRefreshLearning: () => Promise<void>;
    cmdExportLearning: () => Promise<void>;
    cmdResetLearning: () => Promise<void>;
    cmdDeleteLearningEntry: (item: any) => Promise<void>;
}

// ---------------------------------------------------------------------------
// All command IDs registered by the extension
// ---------------------------------------------------------------------------

export const COMMAND_IDS = [
    'literaryCritic.analyze',
    'literaryCritic.resume',
    'literaryCritic.nextFinding',
    'literaryCritic.acceptFinding',
    'literaryCritic.rejectFinding',
    'literaryCritic.discuss',
    'literaryCritic.selectFinding',
    'literaryCritic.reviewFinding',
    'literaryCritic.clearSession',
    'literaryCritic.rerunAnalysisWithUpdatedIndexes',
    'literaryCritic.selectModel',
    'literaryCritic.stopServer',
    'literaryCritic.refreshSessions',
    'literaryCritic.viewSession',
    'literaryCritic.deleteSession',
    'literaryCritic.refreshLearning',
    'literaryCritic.exportLearning',
    'literaryCritic.resetLearning',
    'literaryCritic.deleteLearningEntry',
] as const;

export type CommandId = typeof COMMAND_IDS[number];

// ---------------------------------------------------------------------------
// Registration function
// ---------------------------------------------------------------------------

/**
 * Register all extension commands and push their disposables to `subscriptions`.
 *
 * Returns the array of disposables so callers can also push them to
 * `context.subscriptions` directly (the function pushes them too for
 * convenience).
 */
export function registerCommands(
    subscriptions: vscode.Disposable[],
    handlers: CommandHandlers,
): vscode.Disposable[] {
    const disposables: vscode.Disposable[] = [
        vscode.commands.registerCommand('literaryCritic.analyze', handlers.cmdAnalyze),
        vscode.commands.registerCommand('literaryCritic.resume', handlers.cmdResume),
        vscode.commands.registerCommand('literaryCritic.nextFinding', handlers.cmdNextFinding),
        vscode.commands.registerCommand('literaryCritic.acceptFinding', handlers.cmdAcceptFinding),
        vscode.commands.registerCommand('literaryCritic.rejectFinding', handlers.cmdRejectFinding),
        vscode.commands.registerCommand('literaryCritic.discuss', handlers.cmdDiscuss),
        vscode.commands.registerCommand('literaryCritic.selectFinding', handlers.cmdSelectFinding),
        vscode.commands.registerCommand('literaryCritic.reviewFinding', handlers.cmdReviewFinding),
        vscode.commands.registerCommand('literaryCritic.clearSession', handlers.cmdClearSession),
        vscode.commands.registerCommand('literaryCritic.rerunAnalysisWithUpdatedIndexes', handlers.cmdRerunAnalysis),
        vscode.commands.registerCommand('literaryCritic.selectModel', handlers.cmdSelectModel),
        vscode.commands.registerCommand('literaryCritic.stopServer', handlers.cmdStopServer),
        // Management commands
        vscode.commands.registerCommand('literaryCritic.refreshSessions', handlers.cmdRefreshSessions),
        vscode.commands.registerCommand('literaryCritic.viewSession', handlers.cmdViewSession),
        vscode.commands.registerCommand('literaryCritic.deleteSession', handlers.cmdDeleteSession),
        vscode.commands.registerCommand('literaryCritic.refreshLearning', handlers.cmdRefreshLearning),
        vscode.commands.registerCommand('literaryCritic.exportLearning', handlers.cmdExportLearning),
        vscode.commands.registerCommand('literaryCritic.resetLearning', handlers.cmdResetLearning),
        vscode.commands.registerCommand('literaryCritic.deleteLearningEntry', handlers.cmdDeleteLearningEntry),
    ];

    subscriptions.push(...disposables);
    return disposables;
}
