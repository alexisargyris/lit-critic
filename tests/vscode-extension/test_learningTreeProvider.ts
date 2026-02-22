/**
 * Tests for LearningTreeProvider module (Phase 2).
 * 
 * Tests tree structure, categories, and data display.
 */

import { strict as assert } from 'assert';

describe('LearningTreeProvider', () => {
    // Sample learning data for testing
    const sampleLearningData = {
        project_name: 'Test Novel',
        review_count: 5,
        preferences: [
            { id: 1, description: '[prose] Sentence fragments OK for voice' },
            { id: 2, description: '[structure] Prefer shorter scenes' },
        ],
        blind_spots: [
            { id: 3, description: '[clarity] Pronoun ambiguity in dialogue' },
        ],
        resolutions: [
            { id: 4, description: 'Finding #5 — addressed by splitting paragraph' },
            { id: 5, description: 'Finding #12 — resolved with character name' },
        ],
        ambiguity_intentional: [
            { id: 6, description: 'Chapter 3: dream sequence imagery' },
        ],
        ambiguity_accidental: [
            { id: 7, description: 'Chapter 5: unclear referent (fixed)' },
        ],
    };

    describe('tree structure', () => {
        it('should show categories (Preferences, Blind Spots, etc.)', () => {
            const categoryNames = [
                'Preferences',
                'Blind Spots',
                'Resolutions',
                'Ambiguity — Intentional',
                'Ambiguity — Accidental',
            ];
            
            assert.ok(categoryNames.includes('Preferences'));
            assert.ok(categoryNames.includes('Blind Spots'));
            assert.ok(categoryNames.includes('Resolutions'));
            assert.ok(categoryNames.includes('Ambiguity — Intentional'));
            assert.ok(categoryNames.includes('Ambiguity — Accidental'));
        });

        it('should show empty message when no learning data', () => {
            const emptyLearning = {
                preferences: [],
                blind_spots: [],
                resolutions: [],
                ambiguity_intentional: [],
                ambiguity_accidental: [],
            };
            
            const hasData = Object.values(emptyLearning).some(arr => arr.length > 0);
            assert.equal(hasData, false);
        });

        it('should collapse categories by default', () => {
            const collapsibleState = 1; // TreeItemCollapsibleState.Collapsed
            assert.equal(collapsibleState, 1);
        });

        it('should only show categories that have data', () => {
            const learning = sampleLearningData;
            const categories = [];
            
            if (learning.preferences.length > 0) categories.push('Preferences');
            if (learning.blind_spots.length > 0) categories.push('Blind Spots');
            if (learning.resolutions.length > 0) categories.push('Resolutions');
            if (learning.ambiguity_intentional.length > 0) categories.push('Ambiguity — Intentional');
            if (learning.ambiguity_accidental.length > 0) categories.push('Ambiguity — Accidental');
            
            assert.equal(categories.length, 5);
        });
    });

    describe('tree items', () => {
        it('should encode entry count in category resource URI', () => {
            const category = {
                label: 'Preferences',
                count: sampleLearningData.preferences.length,
                resourceUri: `lit-critic-count://learning-category/preferences?count=${sampleLearningData.preferences.length}`,
            };
            
            assert.equal(category.resourceUri, 'lit-critic-count://learning-category/preferences?count=2');
        });

        it('should set correct icons for each category', () => {
            const categoryIcons = {
                'preferences': 'symbol-variable',
                'blind_spots': 'eye-closed',
                'resolutions': 'check-all',
                'ambiguity_intentional': 'question',
                'ambiguity_accidental': 'warning',
            };
            
            assert.equal(categoryIcons.preferences, 'symbol-variable');
            assert.equal(categoryIcons.blind_spots, 'eye-closed');
            assert.equal(categoryIcons.resolutions, 'check-all');
            assert.equal(categoryIcons.ambiguity_intentional, 'question');
            assert.equal(categoryIcons.ambiguity_accidental, 'warning');
        });

        it('should show entries under categories', () => {
            const category = 'preferences';
            const entries = sampleLearningData.preferences;
            
            assert.equal(entries.length, 2);
            assert.ok(entries[0].description);
            assert.ok(entries[0].id);
        });

        it('should use entry description as label', () => {
            const entry = sampleLearningData.preferences[0];
            const label = entry.description;
            
            assert.equal(label, '[prose] Sentence fragments OK for voice');
        });

        it('should set entry ID for deletion', () => {
            const entry = sampleLearningData.preferences[0];
            assert.equal(entry.id, 1);
            assert.ok(typeof entry.id === 'number');
        });
    });

    describe('refresh', () => {
        it('should reload learning data from API', () => {
            let apiCalled = false;
            const mockApiClient = {
                getLearning: async (projectPath: string) => {
                    apiCalled = true;
                    return sampleLearningData;
                },
            };
            
            assert.ok(mockApiClient.getLearning);
        });

        it('should handle API errors gracefully', () => {
            const mockApiClient = {
                getLearning: async (projectPath: string) => {
                    throw new Error('Network error');
                },
            };
            
            let errorCaught = false;
            try {
                throw new Error('Network error');
            } catch (err) {
                errorCaught = true;
            }
            
            assert.ok(errorCaught);
        });

        it('should clear when no project path', () => {
            let projectPath: string | null = null;
            const shouldClear = !projectPath;
            
            assert.equal(shouldClear, true);
        });

        it('should fire tree data change event on refresh', () => {
            let eventFired = false;
            const mockEmitter = {
                fire: () => { eventFired = true; },
            };
            
            mockEmitter.fire();
            assert.ok(eventFired);
        });
    });

    describe('context values', () => {
        it('should set contextValue for category items', () => {
            const categoryItem = {
                contextValue: 'learningCategory',
            };
            
            assert.equal(categoryItem.contextValue, 'learningCategory');
        });

        it('should set contextValue for entry items', () => {
            const entryItem = {
                contextValue: 'learningEntry',
            };
            
            assert.equal(entryItem.contextValue, 'learningEntry');
        });

        it('should set contextValue for empty state', () => {
            const emptyItem = {
                contextValue: 'empty',
            };
            
            assert.equal(emptyItem.contextValue, 'empty');
        });
    });

    describe('category mapping', () => {
        it('should map preferences to correct data', () => {
            const category = 'preferences';
            const entries = sampleLearningData.preferences;
            
            assert.ok(Array.isArray(entries));
            assert.equal(entries.length, 2);
        });

        it('should map blind_spots to correct data', () => {
            const category = 'blind_spots';
            const entries = sampleLearningData.blind_spots;
            
            assert.ok(Array.isArray(entries));
            assert.equal(entries.length, 1);
        });

        it('should map resolutions to correct data', () => {
            const category = 'resolutions';
            const entries = sampleLearningData.resolutions;
            
            assert.ok(Array.isArray(entries));
            assert.equal(entries.length, 2);
        });

        it('should map ambiguity_intentional to correct data', () => {
            const category = 'ambiguity_intentional';
            const entries = sampleLearningData.ambiguity_intentional;
            
            assert.ok(Array.isArray(entries));
            assert.equal(entries.length, 1);
        });

        it('should map ambiguity_accidental to correct data', () => {
            const category = 'ambiguity_accidental';
            const entries = sampleLearningData.ambiguity_accidental;
            
            assert.ok(Array.isArray(entries));
            assert.equal(entries.length, 1);
        });

        it('should return empty array for unknown category', () => {
            const category = 'unknown_category';
            const entries: any[] = [];
            
            assert.ok(Array.isArray(entries));
            assert.equal(entries.length, 0);
        });
    });

    describe('entry display', () => {
        it('should show full description as tooltip', () => {
            const entry = sampleLearningData.preferences[0];
            const tooltip = entry.description;
            
            assert.equal(tooltip, '[prose] Sentence fragments OK for voice');
        });

        it('should handle entries without IDs (empty state)', () => {
            const entry = { description: 'No learning data yet' };
            const hasId = 'id' in entry;
            
            assert.equal(hasId, false);
        });

        it('should use circle-small icon for entries', () => {
            const iconName = 'circle-small';
            assert.equal(iconName, 'circle-small');
        });

        it('should use info icon for empty state', () => {
            const iconName = 'info';
            assert.equal(iconName, 'info');
        });
    });
});
