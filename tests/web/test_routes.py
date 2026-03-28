"""
Tests for the lit-critic Web UI.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from fastapi import HTTPException

from web.app import app
from web.routes import session_mgr
from web.session_manager import ResumeScenePathError
from lit_platform.runtime.models import Finding, SessionState, LearningData


class TestIndexPage:
    """Test the main page serves correctly."""

    def test_index_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "lit-critic" in response.text
        assert 'id="sessions-actions-section"' in response.text
        assert 'id="indexes-actions-section"' in response.text
        assert ">Sessions<" in response.text
        assert ">Indexes<" in response.text
        assert ">Analyze<" in response.text
        assert 'id="check-session-btn"' in response.text
        assert ">Check<" in response.text
        assert ">Refresh<" in response.text
        assert ">Audit Quick<" in response.text
        assert "Audit Deep" in response.text


class TestStaticFiles:
    """Test that static files are served."""

    def test_css_served(self, client):
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_js_served(self, client):
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]


