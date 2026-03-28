"""
REST API routes aggregator for the lit-critic Web UI.

This module combines all domain-specific routers into a single router
that is registered with the FastAPI application in app.py.
"""

from fastapi import APIRouter

from .routes_config import router as config_router
from .routes_analysis import router as analysis_router
from .routes_session import router as session_router
from .routes_management import router as management_router

# Re-exported for test and session-manager access
from .route_helpers import session_mgr  # noqa: F401

router = APIRouter(prefix="/api")
router.include_router(config_router)
router.include_router(analysis_router)
router.include_router(session_router)
router.include_router(management_router)
