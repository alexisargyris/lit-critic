/**
 * Real tests for SessionsTreeProvider module.
 *
 * Verifies root scene-group rendering behavior, including multi-file
 * labels ("filename +x") and hover tooltip contents.
 */

import { strict as assert } from 'assert';
import { createFreshMockVscode } from './fixtures';

declare const describe: (name: string, fn: () => void) => void;
declare const beforeEach: (fn: () => void) => void;
declare const it: (name: string, fn: () => Promise<void> | void) => void;

const proxyquire = require('proxyquire').noCallThru();

describe('SessionsTreeProvider (Real)', () => {
    let SessionsTreeProvider: any;
    let mockVscode: any;
    let treeProvider: any;

    beforeEach(() => {
        mockVscode = createFreshMockVscode();

        const module = proxyquire('../../vscode-extension/src/sessionsTreeProvider', {
            vscode: mockVscode,
        });

        SessionsTreeProvider = module.SessionsTreeProvider;
        treeProvider = new SessionsTreeProvider();
    });

    it('shows "filename +x" label for multi-file sessions at root', async () => {
        const apiClient = {
            async listSessions() {
                return {
                    sessions: [
                        {
                            id: 11,
                            status: 'active',
                            scene_path: '/repo/scene-a.txt',
                            scene_paths: ['/repo/scene-a.txt', '/repo/scene-b.txt', '/repo/scene-c.txt'],
                            model: 'sonnet',
                            created_at: '2026-02-20T10:00:00',
                            total_findings: 3,
                            accepted_count: 0,
                            rejected_count: 0,
                            withdrawn_count: 0,
                        },
                    ],
                };
            },
        };

        treeProvider.setApiClient(apiClient);
        treeProvider.setProjectPath('/repo');
        await treeProvider.refresh();

        const roots = treeProvider.getChildren();
        assert.equal(roots.length, 1);
        assert.equal(roots[0].label, 'scene-a.txt +2');
    });

    it('shows all files in root tooltip for multi-file sessions', async () => {
        const apiClient = {
            async listSessions() {
                return {
                    sessions: [
                        {
                            id: 21,
                            status: 'completed',
                            scene_path: '/repo/scene-a.txt',
                            scene_paths: ['/repo/scene-a.txt', '/repo/scene-b.txt', '/repo/scene-c.txt'],
                            model: 'sonnet',
                            created_at: '2026-02-20T10:00:00',
                            completed_at: '2026-02-20T10:20:00',
                            total_findings: 2,
                            accepted_count: 1,
                            rejected_count: 1,
                            withdrawn_count: 0,
                        },
                    ],
                };
            },
        };

        treeProvider.setApiClient(apiClient);
        treeProvider.setProjectPath('/repo');
        await treeProvider.refresh();

        const roots = treeProvider.getChildren();
        assert.equal(roots.length, 1);

        const tooltip = String(roots[0].tooltip ?? '');
        assert.match(tooltip, /Scenes \(3\):/);
        assert.match(tooltip, /scene-a\.txt/);
        assert.match(tooltip, /scene-b\.txt/);
        assert.match(tooltip, /scene-c\.txt/);
    });

    it('renders stale active sessions with warning icon and changed-index tooltip details', async () => {
        const apiClient = {
            async listSessions() {
                return {
                    sessions: [
                        {
                            id: 31,
                            status: 'active',
                            scene_path: '/repo/scene-stale.txt',
                            scene_paths: ['/repo/scene-stale.txt'],
                            model: 'sonnet',
                            created_at: '2026-02-20T11:00:00',
                            total_findings: 4,
                            accepted_count: 1,
                            rejected_count: 1,
                            withdrawn_count: 0,
                            index_context_stale: true,
                            index_changed_files: ['CANON.md', 'GLOSSARY.md'],
                        },
                    ],
                };
            },
        };

        treeProvider.setApiClient(apiClient);
        treeProvider.setProjectPath('/repo');
        await treeProvider.refresh();

        const roots = treeProvider.getChildren();
        assert.equal(roots.length, 1);

        const children = treeProvider.getChildren(roots[0]);
        assert.equal(children.length, 1);

        const sessionItem = children[0];
        assert.match(String(sessionItem.description ?? ''), /active · stale/);
        assert.equal(sessionItem.iconPath?.id, 'warning');

        const tooltip = String(sessionItem.tooltip ?? '');
        assert.match(tooltip, /Status: active \(stale\)/);
        assert.match(tooltip, /Changed indexes: CANON\.md, GLOSSARY\.md/);
    });

    it('returns current session item for native TreeView reveal without synthetic cursor markers', async () => {
        const apiClient = {
            async listSessions() {
                return {
                    sessions: [
                        {
                            id: 41,
                            status: 'active',
                            scene_path: '/repo/scene-a.txt',
                            scene_paths: ['/repo/scene-a.txt'],
                            model: 'sonnet',
                            created_at: '2026-02-20T12:00:00',
                            total_findings: 1,
                            accepted_count: 0,
                            rejected_count: 0,
                            withdrawn_count: 0,
                        },
                    ],
                };
            },
        };

        treeProvider.setApiClient(apiClient);
        treeProvider.setProjectPath('/repo');
        await treeProvider.refresh();
        treeProvider.setCurrentSession(41);

        const current = treeProvider.getCurrentSessionItem();

        assert.ok(current, 'Expected current session item');
        assert.equal(current.label, '#41');
        assert.ok(!String(current.label).includes('▶'));
        assert.equal(current.id, 'session:41');
        assert.notEqual(current.iconPath?.id, 'target');
    });
});
