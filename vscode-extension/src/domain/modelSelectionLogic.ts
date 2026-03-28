export interface AnalysisModelConfigReader {
    inspect<T>(section: string): {
        globalValue?: T;
        workspaceValue?: T;
        workspaceFolderValue?: T;
    } | undefined;
    get<T>(section: string, defaultValue: T): T;
}

type AnalysisMode = 'quick' | 'deep';

/**
 * Resolve configured analysis mode.
 *
 * Preferred key: literaryCritic.analysisMode
 * Default: deep (backward-compatible behavior)
 */
export function getConfiguredAnalysisMode(config: AnalysisModelConfigReader): AnalysisMode {
    const mode = config.get<string>('analysisMode', 'deep');
    if (mode === 'quick' || mode === 'deep') {
        return mode;
    }
    return 'deep';
}

export function buildAnalysisStartStatusMessage(mode: AnalysisMode = 'deep'): string {
    if (mode === 'quick') {
        return 'Running quick analysis...';
    }

    return 'Running deep analysis...';
}
