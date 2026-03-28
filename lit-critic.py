#!/usr/bin/env python3
"""
lit-critic (short for Literary Critic) — Orchestrator

A multi-lens editorial review system for fiction manuscripts.
Runs 7 analytical lenses in parallel, coordinates findings, and presents them interactively.

Usage:
    python lit-critic.py sessions start --scene path/to/scene.txt --project path/to/project/ --mode deep

The project directory should contain:
    - CANON.md              (world rules and invariants — you write this)
    - STYLE.md              (prose rules — you write this)
    - LEARNING.md (optional, exported from learning data)

    Characters, terms, threads, and timeline entries are extracted automatically
    from your prose and stored in the project database (.lit-critic.db).
    You do not need to maintain CAST.md, GLOSSARY.md, THREADS.md, or TIMELINE.md.

This file is a thin wrapper around the lit-critic package.
For the modular implementation, see the core/, lit_platform/, cli/, and web/ directories.
"""

import asyncio
from cli.commands import main

if __name__ == "__main__":
    asyncio.run(main())
