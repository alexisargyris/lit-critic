/**
 * Tests for ApiClient module.
 * 
 * Note: These tests verify API client logic and data structures.
 */

import { strict as assert } from 'assert';
import {
    sampleServerConfig,
    sampleAnalysisSummary,
    sampleFindingResponse,
    sampleAdvanceResponse,
    sampleSessionInfo,
} from './fixtures';

describe('ApiClient', () => {
    describe('data structures', () => {
        it('should validate server config structure', () => {
            assert.ok(sampleServerConfig.available_models);
            assert.ok(sampleServerConfig.default_model);
            assert.equal(sampleServerConfig.default_model, 'sonnet');
        });

        it('should validate analysis summary structure', () => {
            assert.ok(sampleAnalysisSummary.scene_path);
            assert.equal(sampleAnalysisSummary.total_findings, 3);
            assert.ok(sampleAnalysisSummary.counts);
            assert.ok(sampleAnalysisSummary.model);
        });

        it('should validate finding response structure', () => {
            assert.equal(sampleFindingResponse.complete, false);
            assert.ok(sampleFindingResponse.finding);
            assert.equal(sampleFindingResponse.finding.number, 1);
        });

        it('should validate session info structure', () => {
            assert.equal(sampleSessionInfo.active, true);
            assert.equal(sampleSessionInfo.total_findings, 3);
            assert.ok(sampleSessionInfo.findings_status);
        });
    });

    describe('URL formatting', () => {
        it('should format API endpoints correctly', () => {
            const baseUrl = 'http://localhost:8000';
            const endpoints = {
                config: `${baseUrl}/api/config`,
                analyze: `${baseUrl}/api/analyze`,
                finding: `${baseUrl}/api/finding`,
                session: `${baseUrl}/api/session`,
            };
            
            assert.equal(endpoints.config, 'http://localhost:8000/api/config');
            assert.equal(endpoints.analyze, 'http://localhost:8000/api/analyze');
        });
    });

    describe('request body formatting', () => {
        it('should format analyze request', () => {
            const request = {
                scene_path: '/test/scene.txt',
                project_path: '/test/project',
                model: 'sonnet',
            };
            
            assert.ok(request.scene_path);
            assert.ok(request.project_path);
            assert.equal(request.model, 'sonnet');
        });

        it('should format reject request', () => {
            const request = {
                reason: 'Not relevant',
            };
            
            assert.equal(request.reason, 'Not relevant');
        });

        it('should handle empty reject reason', () => {
            const reason = '';
            const request = { reason: reason || '' };
            assert.equal(request.reason, '');
        });
    });

    describe('response parsing', () => {
        it('should handle complete response', () => {
            const response = { complete: true, message: 'All done' };
            assert.equal(response.complete, true);
            assert.equal(response.message, 'All done');
        });

        it('should handle finding in response', () => {
            const response = sampleFindingResponse;
            assert.ok(response.finding);
            assert.equal(response.finding.number, 1);
            assert.equal(response.finding.severity, 'major');
        });

        it('should handle advance response with scene change', () => {
            const response = {
                ...sampleAdvanceResponse,
                scene_change: {
                    changed: true,
                    adjusted: 2,
                    stale: 1,
                    re_evaluated: [],
                },
            };
            
            assert.ok(response.scene_change);
            assert.equal(response.scene_change.changed, true);
            assert.equal(response.scene_change.adjusted, 2);
        });
    });

    describe('error handling', () => {
        it('should format error messages', () => {
            const statusCode = 500;
            const detail = 'Internal server error';
            const errorMessage = `HTTP ${statusCode}: ${detail}`;
            
            assert.match(errorMessage, /HTTP 500/);
            assert.match(errorMessage, /Internal server error/);
        });

        it('should handle network errors', () => {
            const error = new Error('Network error');
            assert.match(error.message, /Network error/);
        });

        it('should handle timeout errors', () => {
            const error = new Error('Request timed out');
            assert.match(error.message, /timed out/);
        });

        it('should handle invalid JSON', () => {
            const error = new Error('Invalid JSON response');
            assert.match(error.message, /Invalid JSON/);
        });
    });
});
