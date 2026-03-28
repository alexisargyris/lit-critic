import { strict as assert } from 'assert';
import { createFreshMockVscode } from './fixtures';

declare const describe: (name: string, fn: () => void) => void;
declare const beforeEach: (fn: () => void) => void;
declare const it: (name: string, fn: () => Promise<void> | void) => void;

const proxyquire = require('proxyquire').noCallThru();

describe('ScenesTreeProvider', () => {
    let ScenesTreeProvider: any;
    let mockVscode: any;
    let treeProvider: any;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();

        const module = proxyquire('../../vscode-extension/src/scenesTreeProvider', {
            vscode: mockVscode,
        });

        ScenesTreeProvider = module.ScenesTreeProvider;
        treeProvider = new ScenesTreeProvider();
    });

    it('shows empty state when there is no project selected', () => {
        // Root now has two group nodes: References and Scenes
        const roots = treeProvider.getChildren();
        assert.equal(roots.length, 2);
        assert.equal(roots[0].label, 'References');
        assert.equal(roots[1].label, 'Scenes');
        // The Scenes group should show the empty-state child
        const sceneChildren = treeProvider.getChildren(roots[1]);
        assert.equal(sceneChildren.length, 1);
        assert.equal(sceneChildren[0].label, 'No scenes found');
        assert.equal(sceneChildren[0].contextValue, 'empty');
    });

    it('loads and sorts scenes from API response', async () => {
        treeProvider.setApiClient({
            async getScenes(projectPath: string) {
                assert.equal(projectPath, '/repo');
                return {
                    scenes: [
                        { scene_path: 'text/chapter-02.txt', scene_id: 'scene-02' },
                        { scene_path: 'text/chapter-01.txt', scene_id: 'scene-01' },
                    ],
                };
            },
            async getIndexes(_projectPath: string) {
                return { indexes: [] };
            },
        });
        treeProvider.setProjectPath('/repo');

        await treeProvider.refresh();

        // Root returns [References, Scenes]; scenes are under the Scenes group
        const roots = treeProvider.getChildren();
        assert.equal(roots.length, 2);
        const sceneChildren = treeProvider.getChildren(roots[1]);
        assert.equal(sceneChildren.length, 2);
        assert.equal(sceneChildren[0].label, 'chapter-01.txt');
        assert.equal(sceneChildren[0].description, 'scene-01');
        assert.equal(sceneChildren[1].label, 'chapter-02.txt');
        assert.equal(sceneChildren[1].description, 'scene-02');
    });

    it('surfaces stale scene with warning icon and stale marker', async () => {
        treeProvider.setApiClient({
            async getScenes() {
                return {
                    scenes: [
                        {
                            scene_path: 'text/chapter-01.txt',
                            scene_id: 'scene-01',
                            stale: true,
                            meta_json: { pov: 'Aria' },
                        },
                    ],
                };
            },
            async getIndexes(_projectPath: string) {
                return { indexes: [] };
            },
        });
        treeProvider.setProjectPath('/repo');

        await treeProvider.refresh();

        const roots = treeProvider.getChildren();
        assert.equal(roots.length, 2);
        const sceneChildren = treeProvider.getChildren(roots[1]);
        assert.equal(sceneChildren.length, 1);
        assert.equal(sceneChildren[0].iconPath?.id, 'warning');
        assert.equal(sceneChildren[0].description, 'scene-01 · stale');
        assert.match(String(sceneChildren[0].tooltip), /Status: stale/);
    });

    it('opens scene file using vscode.open command', async () => {
        treeProvider.setApiClient({
            async getScenes() {
                return {
                    scenes: [{ scene_path: 'text/chapter-01.txt', scene_id: 'scene-01' }],
                };
            },
            async getIndexes(_projectPath: string) {
                return { indexes: [] };
            },
        });
        treeProvider.setProjectPath('/repo');

        await treeProvider.refresh();

        const roots = treeProvider.getChildren();
        const sceneChildren = treeProvider.getChildren(roots[1]);
        const sceneItem = sceneChildren[0];
        assert.equal(sceneItem.command?.command, 'vscode.open');
        assert.equal(
            String(sceneItem.command?.arguments?.[0]?.fsPath).replace(/\\/g, '/'),
            '/repo/text/chapter-01.txt',
        );
    });
});
