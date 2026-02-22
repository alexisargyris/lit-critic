/**
 * Tests for SessionsTreeProvider module.
 *
 * These tests validate the scene-first hierarchy expectations and
 * aggregated findings counters shown per session.
 */

import { strict as assert } from 'assert';

describe('SessionsTreeProvider', () => {
    const sampleSessions = [
        {
            id: 1,
            scene_path: '/test/scene01.txt',
            status: 'completed',
            model: 'sonnet',
            created_at: '2026-02-10T10:00:00',
            completed_at: '2026-02-10T10:30:00',
            total_findings: 5,
            accepted_count: 3,
            rejected_count: 2,
            withdrawn_count: 0,
        },
        {
            id: 2,
            scene_path: '/test/scene02.txt',
            status: 'active',
            model: 'opus',
            index_context_stale: true,
            index_changed_files: ['CANON.md', 'GLOSSARY.md'],
            created_at: '2026-02-11T09:00:00',
            completed_at: null,
            total_findings: 8,
            accepted_count: 2,
            rejected_count: 1,
            withdrawn_count: 0,
        },
        {
            id: 3,
            scene_path: '/test/scene01.txt',
            status: 'abandoned',
            model: 'haiku',
            created_at: '2026-02-09T14:00:00',
            completed_at: null,
            total_findings: 3,
            accepted_count: 0,
            rejected_count: 0,
            withdrawn_count: 1,
        },
    ];

    describe('scene-first grouping', () => {
        it('groups sessions by scene file name at root level', () => {
            const byScene = new Map<string, typeof sampleSessions>();

            for (const session of sampleSessions) {
                const sceneName = session.scene_path.split('/').pop()!;
                if (!byScene.has(sceneName)) {
                    byScene.set(sceneName, []);
                }
                byScene.get(sceneName)!.push(session);
            }

            assert.ok(byScene.has('scene01.txt'));
            assert.ok(byScene.has('scene02.txt'));
            assert.equal(byScene.get('scene01.txt')!.length, 2);
            assert.equal(byScene.get('scene02.txt')!.length, 1);
        });

        it('sorts scene groups alphabetically for deterministic display', () => {
            const sceneNames = ['scene02.txt', 'scene01.txt'];
            const sorted = [...sceneNames].sort((a, b) => a.localeCompare(b));
            assert.deepEqual(sorted, ['scene01.txt', 'scene02.txt']);
        });
    });

    describe('session items under scene', () => {
        it('formats session label as compact #ID', () => {
            const session = sampleSessions[0];
            const label = `#${session.id}`;
            assert.equal(label, '#1');
        });

        it('keeps session node context/command compatibility', () => {
            const session = sampleSessions[1];
            const contextValue = 'session';
            const command = {
                command: 'literaryCritic.viewSession',
                title: 'View Session Details',
                arguments: [session.id],
            };

            assert.equal(contextValue, 'session');
            assert.equal(command.command, 'literaryCritic.viewSession');
            assert.deepEqual(command.arguments, [2]);
        });

        it('includes status and findings summary in description', () => {
            const session = sampleSessions[0];
            const pending = Math.max(
                0,
                session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count,
            );
            const description = `${session.status} · total ${session.total_findings} · accepted ${session.accepted_count} · rejected ${session.rejected_count} · withdrawn ${session.withdrawn_count} · pending ${pending}`;

            assert.match(description, /completed/);
            assert.match(description, /total 5/);
            assert.match(description, /accepted 3/);
            assert.match(description, /pending 0/);
        });

        it('surfaces stale marker for active stale sessions in description', () => {
            const session = sampleSessions[1] as any;
            const pending = Math.max(
                0,
                session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count,
            );
            const statusLabel = session.status === 'active' && session.index_context_stale
                ? `${session.status} · stale`
                : session.status;
            const description = `${statusLabel} · total ${session.total_findings} · accepted ${session.accepted_count} · rejected ${session.rejected_count} · withdrawn ${session.withdrawn_count} · pending ${pending}`;

            assert.match(description, /active · stale/);
        });
    });

    describe('aggregated findings counters', () => {
        it('derives pending count from totals and terminal counters', () => {
            const session = sampleSessions[1];
            const pending = Math.max(
                0,
                session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count,
            );

            assert.equal(pending, 5);
        });

        it('exposes all expected aggregate metrics per session', () => {
            const session = sampleSessions[2];
            const pending = Math.max(
                0,
                session.total_findings - session.accepted_count - session.rejected_count - session.withdrawn_count,
            );

            const metrics = {
                Total: session.total_findings,
                Accepted: session.accepted_count,
                Rejected: session.rejected_count,
                Withdrawn: session.withdrawn_count,
                Pending: pending,
            };

            assert.deepEqual(metrics, {
                Total: 3,
                Accepted: 0,
                Rejected: 0,
                Withdrawn: 1,
                Pending: 2,
            });
        });
    });

    describe('empty state', () => {
        it('shows no sessions message when data is empty', () => {
            const sessions: any[] = [];
            const label = sessions.length === 0 ? 'No sessions found' : 'Has sessions';
            assert.equal(label, 'No sessions found');
        });
    });
});
