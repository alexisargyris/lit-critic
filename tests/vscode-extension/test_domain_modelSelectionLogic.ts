import { strict as assert } from 'assert';

import {
    buildAnalysisStartStatusMessage,
    getConfiguredAnalysisMode,
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
    it('uses deep as default analysis mode', () => {
        const config = makeConfig({ values: {} });
        assert.equal(getConfiguredAnalysisMode(config), 'deep');
    });

    it('returns configured analysis mode when valid', () => {
        const config = makeConfig({ values: { analysisMode: 'quick' } });
        assert.equal(getConfiguredAnalysisMode(config), 'quick');
    });

    it('falls back to deep for invalid analysis mode values', () => {
        const config = makeConfig({ values: { analysisMode: 'turbo' } });
        assert.equal(getConfiguredAnalysisMode(config), 'deep');
    });

    it('builds quick status message', () => {
        const message = buildAnalysisStartStatusMessage('quick');
        assert.equal(message, 'Running quick analysis...');
    });

    it('builds deep status message by default', () => {
        const message = buildAnalysisStartStatusMessage();
        assert.equal(message, 'Running deep analysis...');
    });

});
