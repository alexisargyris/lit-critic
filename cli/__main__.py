"""
Entry point for running lit-critic as a module.

Usage:
    python -m lit-critic --scene path/to/scene.txt --project path/to/project/
"""

import asyncio
from .interface import main

if __name__ == "__main__":
    asyncio.run(main())
