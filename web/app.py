"""
FastAPI application setup for the lit-critic Web UI.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from . import __version__ as WEB_VERSION
from .routes import router

# Load .env file (if present) so ANTHROPIC_API_KEY is available via os.environ
load_dotenv()

# Paths
WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

# App
app = FastAPI(
    title="lit-critic",
    description="Multi-lens editorial review system for fiction manuscripts",
    version=WEB_VERSION,
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Include API routes
app.include_router(router)


@app.get("/")
async def index(request: Request):
    """Serve the main page."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/sessions")
async def sessions_page(request: Request):
    """Serve the sessions management page."""
    return templates.TemplateResponse(request, "sessions.html")


@app.get("/learning")
async def learning_page(request: Request):
    """Serve the learning management page."""
    return templates.TemplateResponse(request, "learning.html")
