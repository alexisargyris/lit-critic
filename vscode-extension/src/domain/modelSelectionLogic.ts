import { ServerConfig } from '../types';

export interface AnalysisModelConfigReader {
    inspect<T>(section: string): {
        globalValue?: T;
        workspaceValue?: T;
        workspaceFolderValue?: T;
    } | undefined;
    get<T>(section: string, defaultValue: T): T;
}

export function resolvePreferredModel(
    configuredModel: string,
    serverConfig: ServerConfig,
): string {
    const available = serverConfig.available_models || {};
    if (configuredModel && Object.prototype.hasOwnProperty.call(available, configuredModel)) {
        return configuredModel;
    }
    if (serverConfig.default_model && Object.prototype.hasOwnProperty.call(available, serverConfig.default_model)) {
        return serverConfig.default_model;
    }
    const first = Object.keys(available)[0];
    return first || configuredModel || serverConfig.default_model;
}

/**
 * Resolve configured analysis model with backward compatibility.
 *
 * Preferred key: literaryCritic.analysisModel
 * Legacy fallback: literaryCritic.model
 */
export function getConfiguredAnalysisModel(config: AnalysisModelConfigReader): string {
    const analysisInspect = config.inspect<string>('analysisModel');
    const analysisIsExplicitlySet = Boolean(
        analysisInspect && (
            analysisInspect.globalValue !== undefined
            || analysisInspect.workspaceValue !== undefined
            || analysisInspect.workspaceFolderValue !== undefined
        )
    );

    if (analysisIsExplicitlySet) {
        return config.get<string>('analysisModel', 'sonnet');
    }

    // Backward-compatible fallback for older workspaces using literaryCritic.model
    return config.get<string>('model', config.get<string>('analysisModel', 'sonnet'));
}

export function buildAnalysisStartStatusMessage(lensPreset: string, serverConfig?: ServerConfig): string {
    const weights = serverConfig?.lens_presets?.[lensPreset];
    if (!weights) {
        return `Running analysis (${lensPreset} preset)...`;
    }

    const activeLensCount = Object.values(weights).filter((value) => Number(value) > 0).length;
    if (activeLensCount <= 0) {
        return `Running analysis (${lensPreset} preset)...`;
    }

    const lensWord = activeLensCount === 1 ? 'lens' : 'lenses';
    return `Running ${activeLensCount} ${lensWord} (${lensPreset} preset)...`;
}
