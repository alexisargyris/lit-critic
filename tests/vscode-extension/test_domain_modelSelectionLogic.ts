import { strict as assert } from 'assert';

import {
    buildAnalysisStartStatusMessage,
    getConfiguredAnalysisModel,
    resolvePreferredModel,
} from '../../vscode-extension/src/domain/modelSelectionLogic';

function makeConfig(overrides: {
    inspect?: any;
    values?: Record<string, string>;
} = {}) {
    const values = overrides.values || {};
    return {
        inspect<T>(_section: string): {
            globalValue?: T;
            workspaceValue?: T;
            workspaceFolderValue?: T;
        } | undefined {
            return overrides.inspect;
        },
        get<T>(section: string, defaultValue: T): T {
            if (Object.prototype.hasOwnProperty.call(values, section)) {
                return values[section] as unknown as T;
            }

            return Object.prototype.hasOwnProperty.call(values, section)
                ? (values[section] as unknown as T)
                : defaultValue;
        },
    };
}

describe('domain/modelSelectionLogic', () => {
    it('uses analysisModel when explicitly configured', () => {
        const config = makeConfig({
            inspect: { workspaceValue: 'opus' },
            values: { analysisModel: 'opus', model: 'haiku' },
        });

        assert.equal(getConfiguredAnalysisModel(config), 'opus');
    });

    it('falls back to legacy model when analysisModel is not explicitly set', () => {
        const config = makeConfig({
            inspect: undefined,
            values: { model: 'haiku' },
        });

        assert.equal(getConfiguredAnalysisModel(config), 'haiku');
    });

    it('builds preset message with active lens count when weights exist', () => {
        const message = buildAnalysisStartStatusMessage('balanced', {
            api_key_configured: true,
            available_models: {},
            default_model: 'sonnet',
            lens_presets: {
                balanced: { prose: 1, structure: 0, dialogue: 1 },
            },
        });

        assert.equal(message, 'Running 2 lenses (balanced preset)...');
    });

    it('falls back to generic preset message when no active lenses exist', () => {
        const message = buildAnalysisStartStatusMessage('balanced', {
            api_key_configured: true,
            available_models: {},
            default_model: 'sonnet',
            lens_presets: {
                balanced: { prose: 0, structure: 0 },
            },
        });

        assert.equal(message, 'Running analysis (balanced preset)...');
    });

    it('resolvePreferredModel keeps configured model when available', () => {
        const selected = resolvePreferredModel('sonnet', {
            api_key_configured: true,
            available_models: {
                sonnet: { label: 'Sonnet' },
                opus: { label: 'Opus' },
            },
            default_model: 'opus',
        });

        assert.equal(selected, 'sonnet');
    });

    it('resolvePreferredModel falls back to backend default when configured missing', () => {
        const selected = resolvePreferredModel('legacy-model', {
            api_key_configured: true,
            available_models: {
                sonnet: { label: 'Sonnet' },
                opus: { label: 'Opus' },
            },
            default_model: 'opus',
        });

        assert.equal(selected, 'opus');
    });

    it('resolvePreferredModel falls back to first available when default missing', () => {
        const selected = resolvePreferredModel('legacy-model', {
            api_key_configured: true,
            available_models: {
                sonnet: { label: 'Sonnet' },
            },
            default_model: 'ghost',
        });

        assert.equal(selected, 'sonnet');
    });
});
