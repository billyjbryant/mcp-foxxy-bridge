#
# MCP Foxxy Bridge - Stdio Client Wrapper with Logging Prefixes
#
# Copyright (C) 2024 Billy Bryant
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Enhanced stdio client wrapper that adds server name prefixes to stdout/stderr logs."""

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TextIO

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from anyio.streams.text import TextReceiveStream
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.message import SessionMessage

logger = logging.getLogger(__name__)


class PrefixedLogHandler:
    """Handles stderr output with server name prefixes."""

    def __init__(self, server_name: str, original_errlog: TextIO = sys.stderr) -> None:
        """Initialize the prefixed log handler.

        Args:
            server_name: Name of the server to use as prefix
            original_errlog: Original error log stream (usually stderr)
        """
        self.server_name = server_name
        self.original_errlog = original_errlog
        self.logger = logging.getLogger(f"mcp_foxxy_bridge.servers.{server_name}")

    def write(self, message: str) -> None:
        """Write message with server name prefix."""
        if message.strip():  # Only log non-empty messages
            # Remove trailing newlines for clean logging
            clean_message = message.rstrip("\n\r")
            if clean_message:
                # Use info level for stdout-like content, debug for verbose output
                error_markers = ["error", "exception", "traceback"]
                if any(marker in clean_message.lower() for marker in error_markers):
                    self.logger.error("[%s] %s", self.server_name, clean_message)
                elif any(marker in clean_message.lower() for marker in ["warn", "warning"]):
                    self.logger.warning("[%s] %s", self.server_name, clean_message)
                elif any(marker in clean_message.lower() for marker in ["debug", "trace"]):
                    self.logger.debug("[%s] %s", self.server_name, clean_message)
                else:
                    self.logger.info("[%s] %s", self.server_name, clean_message)

    def flush(self) -> None:
        """Flush the original error log."""
        if hasattr(self.original_errlog, "flush"):
            self.original_errlog.flush()

    def fileno(self) -> int:
        """Return the file descriptor of the underlying stream."""
        return self.original_errlog.fileno()

    def close(self) -> None:
        """Close the underlying stream."""
        if hasattr(self.original_errlog, "close"):
            self.original_errlog.close()

    def readable(self) -> bool:
        """Return whether the stream supports reading."""
        return hasattr(self.original_errlog, "readable") and self.original_errlog.readable()

    def writable(self) -> bool:
        """Return whether the stream supports writing."""
        return hasattr(self.original_errlog, "writable") and self.original_errlog.writable()

    def seekable(self) -> bool:
        """Return whether the stream supports seeking."""
        return hasattr(self.original_errlog, "seekable") and self.original_errlog.seekable()


class StdoutCaptureHandler:
    """Captures and logs stdout from MCP servers with prefixes."""

    def __init__(self, server_name: str) -> None:
        """Initialize stdout capture handler.

        Args:
            server_name: Name of the server to use as prefix
        """
        self.server_name = server_name
        self.logger = logging.getLogger(f"mcp_foxxy_bridge.servers.{server_name}.stdout")

    async def capture_stdout(self, stdout_stream: anyio.abc.ByteReceiveStream) -> None:
        """Capture stdout and log with server prefix.

        Args:
            stdout_stream: The stdout stream from the MCP server process
        """
        try:
            buffer = ""
            async for chunk in TextReceiveStream(stdout_stream, encoding="utf-8", errors="replace"):
                lines = (buffer + chunk).split("\n")
                buffer = lines.pop()

                for line in lines:
                    if line.strip():  # Only log non-empty lines
                        # Check if this looks like a JSON-RPC message (MCP protocol)
                        if line.strip().startswith('{"') and '"jsonrpc"' in line:
                            # This is likely MCP protocol traffic, log at debug level
                            self.logger.debug("[%s] MCP: %s", self.server_name, line.strip())
                        else:
                            # This is likely application output, log at info level
                            self.logger.info("[%s] %s", self.server_name, line.strip())

                # Handle any remaining content in buffer
                if buffer.strip():
                    self.logger.info("[%s] %s", self.server_name, buffer.strip())

        except anyio.ClosedResourceError:
            # Stream was closed, normal during shutdown
            self.logger.debug("[%s] Stdout stream closed", self.server_name)
        except Exception:
            self.logger.exception("[%s] Error capturing stdout", self.server_name)


@asynccontextmanager
async def stdio_client_with_logging(
    server: StdioServerParameters,
    server_name: str,
    errlog: TextIO = sys.stderr,
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
    ],
    None,
]:
    """Enhanced stdio client that adds server name prefixes to stderr logs.

    This is a wrapper around the standard MCP stdio_client that captures
    stderr output and adds server name prefixes for easier debugging.

    Args:
        server: Server parameters for the stdio client
        server_name: Name of the server (used for prefixing logs)
        errlog: Original error log stream

    Yields:
        Tuple of (read_stream, write_stream) for MCP communication
    """
    logger.debug("Starting stdio client with logging for server: %s", server_name)

    # Create a prefixed error log handler
    prefixed_errlog = PrefixedLogHandler(server_name, errlog)

    # Use the standard stdio_client with our prefixed error handler
    async with stdio_client(server, errlog=prefixed_errlog) as (read_stream, write_stream):  # type: ignore[arg-type]
        logger.debug("Stdio client established for server: %s", server_name)
        yield read_stream, write_stream
        logger.debug("Stdio client closing for server: %s", server_name)
