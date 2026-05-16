"""MCP server exposing Lumo tools to any MCP-compatible client.

Public API:
    server  — the FastMCP instance (importable for tests and custom mounts)
    main()  — stdio entrypoint, registered as `lumo-mcp` console script
"""

from lumo.mcp.server import main, server

__all__ = ["main", "server"]
