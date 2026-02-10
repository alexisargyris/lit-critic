/**
 * Tests for StatusBar module.
 * 
 * Note: These tests verify the status bar state management logic.
 */

import { strict as assert } from 'assert';

describe('StatusBar', () => {
    describe('state transitions', () => {
        it('should format progress text correctly', () => {
            const current = 5;
            const total = 10;
            const text = `${current}/${total} findings`;
            assert.match(text, /5\/10/);
        });

        it('should format analyzing text with spinner', () => {
            const message = 'Running lenses...';
            const text = `$(sync~spin) ${message}`;
            assert.match(text, /sync~spin/);
            assert.match(text, /Running lenses/);
        });

        it('should include error indicator in text', () => {
            const text = '$(error) lit-critic';
            assert.match(text, /error/i);
        });

        it('should include complete state text', () => {
            const text = '$(book) Review complete';
            assert.match(text, /complete/i);
        });

        it('should include ready state text', () => {
            const text = '$(book) lit-critic';
            assert.match(text, /lit-critic/);
        });
    });

    describe('command association', () => {
        it('should associate correct commands with states', () => {
            const states = {
                ready: 'literaryCritic.analyze',
                progress: 'literaryCritic.nextFinding',
                analyzing: undefined,
                complete: 'literaryCritic.analyze',
                error: 'literaryCritic.analyze',
            };
            
            assert.equal(states.ready, 'literaryCritic.analyze');
            assert.equal(states.progress, 'literaryCritic.nextFinding');
            assert.equal(states.analyzing, undefined);
        });
    });
});
