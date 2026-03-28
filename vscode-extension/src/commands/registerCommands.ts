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
    cmdNextFinding: () => Promise<void>;
    cmdAcceptFinding: () => Promise<void>;
    cmdRejectFinding: () => Promise<void>;
    cmdDiscuss: () => Promise<void>;
    cmdSelectFinding: (index: number) => Promise<void>;
    cmdReviewFinding: () => Promise<void>;
    cmdSelectModel: () => Promise<void>;
    cmdStopServer: () => void;
    cmdRefreshSessions: () => Promise<void>;
    cmdViewSession: (item: any) => Promise<void>;
    cmdDeleteSession: (item?: any) => Promise<void>;
    cmdRefreshLearning: () => Promise<void>;
    cmdExportLearning: () => Promise<void>;
    cmdResetLearning: () => Promise<void>;
    cmdDeleteLearningEntry: (item: any) => Promise<void>;
    cmdRefreshKnowledge: () => Promise<void>;
    cmdEditKnowledgeEntry?: (item: any) => Promise<void>;
    cmdResetKnowledgeOverride?: (item?: any) => Promise<void>;
    cmdOpenKnowledgeReviewPanel?: (item?: any) => Promise<void>;
    cmdDeleteKnowledgeEntity?: (item: any) => Promise<void>;
    cmdNextKnowledgeEntity?: () => Promise<void>;
    cmdPreviousKnowledgeEntity?: () => Promise<void>;
    cmdToggleEntityLock?: (item?: any) => Promise<void>;
    cmdKeepFlaggedEntity?: (item?: any) => Promise<void>;
    cmdDeleteFlaggedEntity?: (item?: any) => Promise<void>;
    cmdRevealSessionInTree?: (sessionId: number) => void;
    [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// All command IDs registered by the extension
// ---------------------------------------------------------------------------

export const COMMAND_IDS = [
    'literaryCritic.analyze',
    'literaryCritic.nextFinding',
    'literaryCritic.acceptFinding',
    'literaryCritic.rejectFinding',
    'literaryCritic.discuss',
    'literaryCritic.selectFinding',
    'literaryCritic.reviewFinding',
    'literaryCritic.selectModel',
    'literaryCritic.stopServer',
    'literaryCritic.refreshSessions',
    'literaryCritic.viewSession',
    'literaryCritic.deleteSession',
    'literaryCritic.refreshLearning',
    'literaryCritic.exportLearning',
    'literaryCritic.resetLearning',
    'literaryCritic.deleteLearningEntry',
    'literaryCritic.refreshKnowledge',
    'literaryCritic.editKnowledgeEntry',
    'literaryCritic.resetKnowledgeOverride',
    'literaryCritic.deleteKnowledgeEntity',
    'literaryCritic.openKnowledgeReviewPanel',
    'literaryCritic.nextKnowledgeEntity',
    'literaryCritic.previousKnowledgeEntity',
    'literaryCritic.toggleEntityLock',
    'literaryCritic.keepFlaggedEntity',
    'literaryCritic.deleteFlaggedEntity',
    'literaryCritic.revealSessionInTree',
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
        // Internal-only command (no menu contribution)
        vscode.commands.registerCommand('literaryCritic.nextFinding', handlers.cmdNextFinding),
        vscode.commands.registerCommand('literaryCritic.acceptFinding', handlers.cmdAcceptFinding),
        vscode.commands.registerCommand('literaryCritic.rejectFinding', handlers.cmdRejectFinding),
        vscode.commands.registerCommand('literaryCritic.discuss', handlers.cmdDiscuss),
        vscode.commands.registerCommand('literaryCritic.selectFinding', handlers.cmdSelectFinding),
        vscode.commands.registerCommand('literaryCritic.reviewFinding', handlers.cmdReviewFinding),
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
        vscode.commands.registerCommand('literaryCritic.refreshKnowledge', handlers.cmdRefreshKnowledge),
        vscode.commands.registerCommand('literaryCritic.editKnowledgeEntry', handlers.cmdEditKnowledgeEntry ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.resetKnowledgeOverride', handlers.cmdResetKnowledgeOverride ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.deleteKnowledgeEntity', handlers.cmdDeleteKnowledgeEntity ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.openKnowledgeReviewPanel', handlers.cmdOpenKnowledgeReviewPanel ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.nextKnowledgeEntity', handlers.cmdNextKnowledgeEntity ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.previousKnowledgeEntity', handlers.cmdPreviousKnowledgeEntity ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.toggleEntityLock', handlers.cmdToggleEntityLock ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.keepFlaggedEntity', handlers.cmdKeepFlaggedEntity ?? (async () => {})),
        vscode.commands.registerCommand('literaryCritic.deleteFlaggedEntity', handlers.cmdDeleteFlaggedEntity ?? (async () => {})),
        // Internal-only: cross-tree navigation from Findings header to Sessions tree
        vscode.commands.registerCommand('literaryCritic.revealSessionInTree', handlers.cmdRevealSessionInTree ?? ((_: number) => {})),
    ];

    subscriptions.push(...disposables);
    return disposables;
}
