#!/usr/bin/env python3
"""
lit-critic (short for Literary Critic) — Orchestrator

A multi-lens editorial review system for fiction manuscripts.
Runs 5 analytical lenses in parallel, coordinates findings, and presents them interactively.

Usage:
    python lit-critic.py --scene path/to/scene.txt --project path/to/project/

The project directory should contain:
    - CANON.md
    - CAST.md
    - GLOSSARY.md
    - STYLE.md
    - THREADS.md
    - TIMELINE.md
    - LEARNING.md (optional)

This file is a thin wrapper around the lit-critic package.
For the modular implementation, see the server/, cli/, and web/ directories.
"""

import asyncio
from cli.interface import main

if __name__ == "__main__":
    asyncio.run(main())
