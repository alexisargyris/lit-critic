#!/usr/bin/env python3
"""
lit-critic — Web UI

Starts a local web server for the browser-based editorial review interface.
This is an alternative to the CLI (lit-critic.py). Both interfaces
share the same analysis engine, session files, and LEARNING.md format.

Usage:
    python lit-critic-web.py [--port 8000] [--host 127.0.0.1]

Then open http://localhost:8000 in your browser.
"""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="lit-critic — Web UI (local browser interface)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port to serve on (default: 8000)"
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload for development"
    )

    args = parser.parse_args()

    print(f"\n  lit-critic — Web UI")
    print(f"  Open http://{args.host}:{args.port} in your browser\n")

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
