"""Client wrapper modules for MCP Foxxy Bridge.

This module provides client wrapper implementations for different MCP
transport protocols and connection types, including:

- SSE (Server-Sent Events) client wrapper with authentication
- STDIO client wrapper for local process communication
- WebSocket client wrapper for real-time connections
- HTTP client wrapper for request-response patterns

Key Components:
    - sse_client_wrapper: SSE client with OAuth and error handling
    - stdio_client_wrapper: Local process MCP client wrapper
    - websocket_client_wrapper: WebSocket MCP client wrapper
    - http_client_wrapper: HTTP request-response MCP client wrapper

Example:
    from mcp_foxxy_bridge.clients import SSEClientWrapper, STDIOClientWrapper

    sse_client = SSEClientWrapper(server_url="https://api.example.com/v1/sse")
    stdio_client = STDIOClientWrapper(command="python", args=["server.py"])
"""

from .sse_client_wrapper import SSEClientWrapper
from .stdio_client_wrapper import STDIOClientWrapper

__all__ = [
    "SSEClientWrapper",
    "STDIOClientWrapper",
]
