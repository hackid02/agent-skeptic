#!/usr/bin/env python3
"""Launcher for The Skeptic MCP server (Agent OS governance layer).

Run it directly (stdio, for `claude mcp add`), or over streamable-HTTP:

    python3 skeptic_server.py --mode sim
    python3 skeptic_server.py --transport streamable-http --port 8888

Wraps `src.skeptic_mcp.main` so relative imports resolve. Use `--mode auto`
to try the live Binance Agent OS MCP server and fall back to the simulator.
"""
from src.skeptic_mcp import main

if __name__ == "__main__":
    main()
