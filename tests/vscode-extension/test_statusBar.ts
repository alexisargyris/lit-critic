/**
 * Real tests for StatusBar module.
 * 
 * Tests the actual StatusBar class with mocked vscode API.
 */

import { strict as assert } from 'assert';
import { createFreshMockVscode, MockStatusBarItem } from './fixtures';

const proxyquire = require('proxyquire').noCallThru();

describe('StatusBar', () => {
    let StatusBar: any;
    let mockVscode: any;
    let statusBar: any;
    let mockItem: MockStatusBarItem;

    beforeEach(() => {
        // Create fresh mocks for each test
        mockVscode = createFreshMockVscode();
        
        // Capture the status bar item that gets created
        mockItem = new MockStatusBarItem();
        mockVscode.window.createStatusBarItem = () => mockItem;

        // Import the real StatusBar class with mocked vscode
        const module = proxyquire('../../vscode-extension/src/statusBar', {
            'vscode': mockVscode,
        });
        StatusBar = module.StatusBar;
    });

    afterEach(() => {
        if (statusBar) {
            statusBar.dispose();
        }
    });

    describe('constructor', () => {
        it('should create and show status bar item', () => {
            statusBar = new StatusBar();
            
            assert.ok(mockItem.visible, 'Status bar should be visible');
        });

        it('should initialize with ready state', () => {
            statusBar = new StatusBar();
            
            assert.match(mockItem.text, /lit-critic/);
            assert.equal(mockItem.command, undefined);
        });
    });

    describe('setReady()', () => {
        it('should set correct text and tooltip', () => {
            statusBar = new StatusBar();
            statusBar.setReady();
            
            assert.equal(mockItem.text, '$(book) lit-critic');
            assert.equal(mockItem.tooltip, 'lit-critic ready');
            assert.equal(mockItem.command, undefined);
        });
    });

    describe('setAnalyzing()', () => {
        it('should show spinner with custom message', () => {
            statusBar = new StatusBar();
            statusBar.setAnalyzing('Running lenses...');
            
            assert.match(mockItem.text, /\$\(sync~spin\)/);
            assert.match(mockItem.text, /Running lenses/);
            assert.equal(mockItem.tooltip, 'Running lenses...');
            assert.equal(mockItem.command, undefined);
        });

        it('should use default message when none provided', () => {
            statusBar = new StatusBar();
            statusBar.setAnalyzing();
            
            assert.match(mockItem.text, /Analyzing/);
            assert.match(mockItem.tooltip, /Analysis in progress/);
        });
    });

    describe('setProgress()', () => {
        it('should display current/total format', () => {
            statusBar = new StatusBar();
            statusBar.setProgress(3, 10);
            
            assert.equal(mockItem.text, '$(book) 3/10 findings');
            assert.match(mockItem.tooltip, /3 of 10 findings reviewed/);
            assert.equal(mockItem.command, undefined);
        });

        it('should handle different numbers correctly', () => {
            statusBar = new StatusBar();
            statusBar.setProgress(1, 1);
            
            assert.equal(mockItem.text, '$(book) 1/1 findings');
        });
    });

    describe('setComplete()', () => {
        it('should show completion message', () => {
            statusBar = new StatusBar();
            statusBar.setComplete();
            
            assert.equal(mockItem.text, '$(book) Review complete');
            assert.match(mockItem.tooltip, /All findings have been reviewed/);
            assert.equal(mockItem.command, undefined);
        });
    });

    describe('setError()', () => {
        it('should show error indicator with message', () => {
            statusBar = new StatusBar();
            const errorMsg = 'Server connection failed';
            statusBar.setError(errorMsg);
            
            assert.match(mockItem.text, /\$\(error\)/);
            assert.match(mockItem.text, /lit-critic/);
            assert.equal(mockItem.tooltip, errorMsg);
            assert.equal(mockItem.command, undefined);
        });
    });

    describe('command state', () => {
        it('should never set commands (all states are informational)', () => {
            statusBar = new StatusBar();
            
            // Test all state transitions
            statusBar.setReady();
            assert.equal(mockItem.command, undefined);
            
            statusBar.setAnalyzing('test');
            assert.equal(mockItem.command, undefined);
            
            statusBar.setProgress(1, 5);
            assert.equal(mockItem.command, undefined);
            
            statusBar.setComplete();
            assert.equal(mockItem.command, undefined);
            
            statusBar.setError('test error');
            assert.equal(mockItem.command, undefined);
        });
    });

    describe('dispose()', () => {
        it('should dispose the status bar item', () => {
            statusBar = new StatusBar();
            statusBar.dispose();
            
            assert.equal(mockItem.visible, false);
        });
    });
});
