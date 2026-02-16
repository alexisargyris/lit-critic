"""
lit-critic - CLI Frontend

Command-line interface for the lit-critic editorial review system.
"""

__version__ = "2.0.1"

from .commands import main  # noqa: F401 — exposed for entry points
