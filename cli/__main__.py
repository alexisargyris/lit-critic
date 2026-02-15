"""
Entry point for running lit-critic as a module.

Usage:
    python -m cli analyze --scene path/to/scene.txt --project path/to/project/
    python -m cli resume --project path/to/project/
    python -m cli sessions list --project path/to/project/
    python -m cli learning view --project path/to/project/
"""

import asyncio
from .commands import main

if __name__ == "__main__":
    asyncio.run(main())
