import { ApiClient } from '../apiClient';
import { ScenesTreeProvider } from '../scenesTreeProvider';
import { KnowledgeTreeProvider } from '../knowledgeTreeProvider';
import { SessionsTreeProvider } from '../sessionsTreeProvider';
import { StalenessRegistry } from './stalenessRegistry';

// ---------------------------------------------------------------------------
// Deps interface
// ---------------------------------------------------------------------------

export interface StalenessServiceDeps {
    detectProjectPath: () => string | undefined;
    getServerManager: () => { isRunning: boolean } | undefined;
    ensureApiClient: () => ApiClient;
    stalenessRegistry: StalenessRegistry;
    scenesTreeProvider: ScenesTreeProvider;
    knowledgeTreeProvider: KnowledgeTreeProvider;
    sessionsTreeProvider: SessionsTreeProvider;
}

// ---------------------------------------------------------------------------
// recheckStaleness
// ---------------------------------------------------------------------------

/**
 * Re-query input staleness from the backend and push the results to all tree
 * providers. Called automatically after knowledge refresh and session re-run.
 * Returns the count of stale inputs found (0 = everything up to date).
 */
export async function recheckStaleness(deps: StalenessServiceDeps): Promise<number> {
    const projectPath = deps.detectProjectPath();
    if (!projectPath || !deps.getServerManager()?.isRunning) {
        return 0;
    }

    const client = deps.ensureApiClient();
    const result = await client.getInputStaleness(projectPath);
    deps.stalenessRegistry.update(result.stale_inputs);

    // Push stale input paths to ScenesTreeProvider
    const staleInputPaths = new Set(result.stale_inputs.map((e) => e.path));
    deps.scenesTreeProvider.setStaleInputPaths(staleInputPaths);

    // Push stale entity keys to KnowledgeTreeProvider
    const hasAllStale = result.stale_inputs.some((e) => e.affected_knowledge === 'all');
    deps.knowledgeTreeProvider.setAllEntitiesStale(hasAllStale);
    if (!hasAllStale) {
        const staleEntityKeys = new Set<string>();
        for (const entry of result.stale_inputs) {
            const affected = entry.affected_knowledge;
            if (Array.isArray(affected)) {
                for (const k of affected) {
                    staleEntityKeys.add(`${k.category}:${k.entity_key}`);
                }
            }
        }
        deps.knowledgeTreeProvider.setStaleEntityKeys(staleEntityKeys);
    }

    // Push stale session IDs to SessionsTreeProvider
    const staleSessionIds = new Set<number>();
    for (const entry of result.stale_inputs) {
        for (const id of entry.affected_sessions) {
            staleSessionIds.add(id);
        }
    }
    deps.sessionsTreeProvider.setStaleSessions(staleSessionIds);

    // Refresh all trees with latest data
    deps.scenesTreeProvider.setApiClient(client);
    deps.scenesTreeProvider.setProjectPath(projectPath);
    await deps.scenesTreeProvider.refresh();
    deps.knowledgeTreeProvider.setApiClient(client);
    deps.knowledgeTreeProvider.setProjectPath(projectPath);
    await deps.knowledgeTreeProvider.refresh();
    deps.sessionsTreeProvider.setApiClient(client);
    deps.sessionsTreeProvider.setProjectPath(projectPath);
    await deps.sessionsTreeProvider.refresh();

    return result.stale_inputs.length;
}
