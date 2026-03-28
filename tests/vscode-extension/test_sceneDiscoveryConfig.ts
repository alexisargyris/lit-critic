import { strict as assert } from 'assert';

const proxyquire = require('proxyquire').noCallThru();

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeConfigStub(overrides: Record<string, unknown> = {}) {
    return {
        get: (key: string, defaultValue: unknown) => {
            return key in overrides ? overrides[key] : defaultValue;
        },
        inspect: () => undefined,
    };
}

function loadModule(configStub?: ReturnType<typeof makeConfigStub>) {
    const mockVscode = {
        workspace: {
            getConfiguration: () => configStub ?? makeConfigStub(),
        },
    };
    return proxyquire('../../vscode-extension/src/bootstrap/sceneDiscoveryConfig', {
        vscode: mockVscode,
    });
}

// ─── normalizeSceneFolder ────────────────────────────────────────────────────

describe('sceneDiscoveryConfig — normalizeSceneFolder()', () => {
    let mod: any;
    before(() => { mod = loadModule(); });

    it('returns the trimmed value when non-empty', () => {
        assert.equal(mod.normalizeSceneFolder('chapters'), 'chapters');
        assert.equal(mod.normalizeSceneFolder('  chapters  '), 'chapters');
    });

    it('falls back to DEFAULT_SCENE_FOLDER for empty string', () => {
        assert.equal(mod.normalizeSceneFolder(''), mod.DEFAULT_SCENE_FOLDER);
    });

    it('falls back to DEFAULT_SCENE_FOLDER for whitespace-only string', () => {
        assert.equal(mod.normalizeSceneFolder('   '), mod.DEFAULT_SCENE_FOLDER);
    });

    it('falls back to DEFAULT_SCENE_FOLDER for undefined', () => {
        assert.equal(mod.normalizeSceneFolder(undefined), mod.DEFAULT_SCENE_FOLDER);
    });
});

// ─── normalizeSceneExtensions ────────────────────────────────────────────────

describe('sceneDiscoveryConfig — normalizeSceneExtensions()', () => {
    let mod: any;
    before(() => { mod = loadModule(); });

    it('returns cleaned extensions when valid', () => {
        assert.deepEqual(mod.normalizeSceneExtensions(['txt', 'md']), ['txt', 'md']);
    });

    it('strips leading dots', () => {
        assert.deepEqual(mod.normalizeSceneExtensions(['.txt', '..md']), ['txt', 'md']);
    });

    it('lower-cases extensions', () => {
        assert.deepEqual(mod.normalizeSceneExtensions(['TXT', 'MD']), ['txt', 'md']);
    });

    it('deduplicates extensions', () => {
        assert.deepEqual(mod.normalizeSceneExtensions(['txt', 'TXT', '.txt']), ['txt']);
    });

    it('skips empty/whitespace-only entries', () => {
        assert.deepEqual(mod.normalizeSceneExtensions(['txt', '', '  ', 'md']), ['txt', 'md']);
    });

    it('falls back to DEFAULT_SCENE_EXTENSIONS for an empty array', () => {
        assert.deepEqual(mod.normalizeSceneExtensions([]), [...mod.DEFAULT_SCENE_EXTENSIONS]);
    });

    it('falls back to DEFAULT_SCENE_EXTENSIONS when all entries are blank', () => {
        assert.deepEqual(mod.normalizeSceneExtensions(['', '   ']), [...mod.DEFAULT_SCENE_EXTENSIONS]);
    });

    it('falls back to DEFAULT_SCENE_EXTENSIONS for undefined', () => {
        assert.deepEqual(mod.normalizeSceneExtensions(undefined), [...mod.DEFAULT_SCENE_EXTENSIONS]);
    });

    it('falls back to DEFAULT_SCENE_EXTENSIONS for non-array input', () => {
        assert.deepEqual(mod.normalizeSceneExtensions('txt'), [...mod.DEFAULT_SCENE_EXTENSIONS]);
    });
});

// ─── getSceneDiscoverySettingsFromConfig ─────────────────────────────────────

describe('sceneDiscoveryConfig — getSceneDiscoverySettingsFromConfig()', () => {
    it('returns normalised defaults when config values are not set', () => {
        const mod = loadModule(makeConfigStub());
        const result = mod.getSceneDiscoverySettingsFromConfig();
        assert.equal(result.sceneFolder, 'text');
        assert.deepEqual(result.sceneExtensions, ['txt']);
    });

    it('returns configured folder when set', () => {
        const mod = loadModule(makeConfigStub({ sceneFolder: 'chapters' }));
        const result = mod.getSceneDiscoverySettingsFromConfig();
        assert.equal(result.sceneFolder, 'chapters');
    });

    it('falls back to default when configured folder is empty', () => {
        const mod = loadModule(makeConfigStub({ sceneFolder: '' }));
        const result = mod.getSceneDiscoverySettingsFromConfig();
        assert.equal(result.sceneFolder, 'text');
    });

    it('returns configured extensions when set', () => {
        const mod = loadModule(makeConfigStub({ sceneExtensions: ['md', 'txt'] }));
        const result = mod.getSceneDiscoverySettingsFromConfig();
        assert.deepEqual(result.sceneExtensions, ['md', 'txt']);
    });

    it('strips leading dots from configured extensions', () => {
        const mod = loadModule(makeConfigStub({ sceneExtensions: ['.md', '.txt'] }));
        const result = mod.getSceneDiscoverySettingsFromConfig();
        assert.deepEqual(result.sceneExtensions, ['md', 'txt']);
    });

    it('falls back to default extensions when configured list is empty', () => {
        const mod = loadModule(makeConfigStub({ sceneExtensions: [] }));
        const result = mod.getSceneDiscoverySettingsFromConfig();
        assert.deepEqual(result.sceneExtensions, ['txt']);
    });
});
