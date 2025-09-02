#
# MCP Foxxy Bridge - STDIO Client Wrapper
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
"""STDIO Client Wrapper for Local Process Communication.

This module provides a wrapper for STDIO-based MCP client connections,
enabling communication with local MCP server processes through standard
input/output streams.

Key Features:
    - Process lifecycle management
    - Environment variable configuration
    - Working directory control
    - Resource cleanup and error handling
    - Comprehensive logging with process context

Example:
    Basic STDIO connection:

    >>> client = STDIOClientWrapper(
    ...     command="python",
    ...     args=["server.py"],
    ...     server_name="local-server"
    ... )
    >>> async with client.connect() as (read_stream, write_stream):
    ...     # Use streams for MCP communication

    With environment variables:

    >>> client = STDIOClientWrapper(
    ...     command="node",
    ...     args=["dist/index.js"],
    ...     server_name="node-server",
    ...     env={"NODE_ENV": "production", "DEBUG": "mcp:*"}
    ... )
"""

import contextlib
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from anyio.streams.memory import (
    MemoryObjectReceiveStream,
    MemoryObjectSendStream,
)
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import JSONRPCMessage

from mcp_foxxy_bridge.utils.logging import get_logger, server_context

logger = get_logger(__name__, facility="CLIENT")


class STDIOClientWrapper:
    """Enhanced STDIO client wrapper for local MCP server processes.

    Attributes:
        command: The command to execute for the MCP server
        args: Command-line arguments for the server process
        server_name: Human-readable server name for logging
        cwd: Working directory for the server process
        env: Environment variables for the server process

    Example:
        >>> client = STDIOClientWrapper(
        ...     command="python",
        ...     args=["-m", "my_mcp_server"],
        ...     server_name="python-server",
        ...     cwd="/path/to/server",
        ...     env={"PYTHONPATH": "/custom/path"}
        ... )
        >>> async with client.connect() as (read_stream, write_stream):
        ...     # Use streams for MCP protocol communication
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        server_name: str = "stdio-server",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize STDIO client wrapper.

        Args:
            command: The command to execute (e.g., "python", "node", "./server")
            args: Command-line arguments for the server process
            server_name: Human-readable server name for logging and identification
            cwd: Working directory for the server process (defaults to current directory)
            env: Environment variables for the server process (merged with os.environ)
            timeout: Timeout for process startup in seconds
        """
        self.command = command
        self.args = args or []
        self.server_name = server_name
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.timeout = timeout

        # Merge environment variables
        self.env = os.environ.copy()
        if env:
            self.env.update(env)

        logger.debug(f"Initialized STDIOClientWrapper for server: {server_name}")
        logger.debug(f"Command: {command} {' '.join(self.args)}")
        logger.debug(f"Working directory: {self.cwd}")

    @contextlib.asynccontextmanager
    async def connect(
        self,
    ) -> AsyncGenerator[
        tuple[
            MemoryObjectReceiveStream[JSONRPCMessage],
            MemoryObjectSendStream[JSONRPCMessage],
        ],
        None,
    ]:
        """Establish STDIO connection to local MCP server process.

        Starts the server process and establishes communication streams
        with comprehensive error handling and resource cleanup.

        Yields:
            tuple of (read_stream, write_stream) for MCP communication

        Raises:
            ProcessError: If server process cannot be started
            TimeoutError: If process startup times out

        Example:
            >>> async with client.connect() as (read_stream, write_stream):
            ...     # Use streams for MCP protocol communication
            ...     await write_stream.send(initialize_request)
            ...     response = await read_stream.receive()
        """
        with server_context(self.server_name):
            logger.debug(f"Starting STDIO client for server: {self.server_name}")

            try:
                async with stdio_client_with_logging(
                    command=self.command,
                    args=self.args,
                    server_name=self.server_name,
                    cwd=str(self.cwd),
                    env=self.env,
                    timeout=self.timeout,
                ) as streams:
                    yield streams

            except Exception as e:
                logger.exception(f"STDIO client failed for server '{self.server_name}': {e}")
                raise


@contextlib.asynccontextmanager
async def stdio_client_with_logging(
    command: str,
    args: list[str] | None = None,
    server_name: str = "stdio-server",
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[JSONRPCMessage],
        MemoryObjectSendStream[JSONRPCMessage],
    ],
    None,
]:
    """Enhanced STDIO client with comprehensive process management and logging.

    This function provides the core STDIO client functionality with detailed
    logging, process lifecycle management, and robust error handling.

    Args:
        command: The command to execute for the MCP server
        args: Command-line arguments for the server process
        server_name: Human-readable server name for logging purposes
        cwd: Working directory for the server process
        env: Environment variables for the server process
        timeout: Timeout for process startup in seconds

    Yields:
        tuple of (read_stream, write_stream) for MCP communication

    Raises:
        ProcessError: If server process cannot be started or fails
        TimeoutError: If process startup exceeds timeout

    Example:
        Python MCP server:

        >>> async with stdio_client_with_logging(
        ...     command="python",
        ...     args=["-m", "my_mcp_server"],
        ...     server_name="python-server"
        ... ) as (read_stream, write_stream):
        ...     # Server process is running and streams are available

        Node.js MCP server:

        >>> async with stdio_client_with_logging(
        ...     command="node",
        ...     args=["dist/server.js"],
        ...     server_name="node-server",
        ...     env={"NODE_ENV": "production"}
        ... ) as streams:
        ...     # Server process with custom environment
    """
    with server_context(server_name):
        full_command = [command] + (args or [])
        logger.debug(f"Starting STDIO server process: {' '.join(full_command)}")
        logger.debug(f"Server name: {server_name}")
        logger.debug(f"Working directory: {cwd or 'current'}")

        if env:
            # Log only custom environment variables (not the full environment)
            custom_env = {k: v for k, v in env.items() if k not in os.environ or os.environ[k] != v}
            if custom_env:
                logger.debug(f"Custom environment variables: {list(custom_env.keys())}")

        try:
            # Validate command and working directory
            await _validate_stdio_configuration(command, cwd, server_name)

            # Prepare environment to suppress child process output and integrate with bridge logging
            clean_env = env.copy() if env else {}

            # Get effective log level (this should come from server config)
            effective_log_level = clean_env.get("MCP_SERVER_LOG_LEVEL", "ERROR")

            # Add logging configuration for common frameworks used by MCP servers
            clean_env.update(
                {
                    "PYTHONUNBUFFERED": "1",  # Enable unbuffered output for real-time logging
                    "MCP_LOG_LEVEL": effective_log_level,
                    "UVICORN_LOG_LEVEL": effective_log_level.lower(),
                    "FASTAPI_LOG_LEVEL": effective_log_level.lower(),
                    "LOGURU_LEVEL": effective_log_level,
                    "LOG_LEVEL": effective_log_level,
                    # Specifically target MCP server library logging
                    "MCP_SERVER_LOG_LEVEL": effective_log_level,
                    "MCP_LOWLEVEL_LOG_LEVEL": "ERROR",  # Always suppress lowlevel processing logs
                    "PYTHON_LOG_LEVEL": effective_log_level,
                    "PYTHONWARNINGS": "ignore",  # Suppress Python warnings unless DEBUG
                    # Add server identification for logging
                    "MCP_SERVER_NAME": server_name,
                    "MCP_BRIDGE_CHILD": "1",  # Identify as bridge child process
                    # Additional environment variables to suppress common server startup logs
                    "FASTMCP_QUIET": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    "FASTMCP_NO_BANNER": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    "MCP_QUIET": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    "MCP_NO_BANNER": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    "SLACK_LOG_LEVEL": effective_log_level,
                    "NODE_ENV": "production" if effective_log_level.upper() != "DEBUG" else "development",
                    # Suppress various server framework startup messages
                    "UVICORN_QUIET": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    "SUPPRESS_STARTUP_LOGS": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    # Suppress npm/node package manager logs
                    "NPM_CONFIG_LOGLEVEL": "error" if effective_log_level.upper() != "DEBUG" else "info",
                    # Don't use --quiet in NODE_OPTIONS as it's not allowed, use other options instead
                    "NODE_NO_WARNINGS": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    # Suppress UV package manager output
                    "UV_NO_PROGRESS": "1" if effective_log_level.upper() != "DEBUG" else "0",
                    # Set signals to handle graceful shutdown
                    "PYTHONDONTWRITEBYTECODE": "1",  # Prevent .pyc files from being created
                    "PYTHONIOENCODING": "utf-8",  # Ensure consistent encoding
                }
            )

            # Enable more verbose logging for DEBUG level
            if effective_log_level.upper() == "DEBUG":
                clean_env["PYTHONWARNINGS"] = "default"

            # Create StdioServerParameters and start the server process
            server_params = StdioServerParameters(command=command, args=args or [], env=clean_env, cwd=cwd)

            async with stdio_client(server_params) as (read_stream, write_stream):
                logger.debug(f"STDIO server process started successfully: {server_name}")
                logger.debug(f"Process streams established for server: {server_name}")

                try:
                    yield (read_stream, write_stream)
                finally:
                    logger.debug(f"STDIO streams closed for server: {server_name}")

        except FileNotFoundError as e:
            error_msg = f"Command not found: {command}"
            logger.exception(f"STDIO server startup failed for '{server_name}': {error_msg}")
            msg = f"Server process startup failed: {error_msg}"
            raise ProcessError(msg) from e

        except PermissionError as e:
            error_msg = f"Permission denied executing: {command}"
            logger.exception(f"STDIO server startup failed for '{server_name}': {error_msg}")
            msg = f"Server process startup failed: {error_msg}"
            raise ProcessError(msg) from e

        except TimeoutError as e:
            error_msg = f"Process startup timeout after {timeout} seconds"
            logger.exception(f"STDIO server startup failed for '{server_name}': {error_msg}")
            msg = f"Server process startup timeout: {error_msg}"
            raise TimeoutError(msg) from e

        except Exception as e:
            logger.exception(f"STDIO server failed for '{server_name}': {e}")
            msg = f"Server process failed: {e}"
            raise ProcessError(msg) from e

        finally:
            logger.debug(f"STDIO client cleanup completed for server: {server_name}")


# Helper functions and validation


async def _validate_stdio_configuration(
    command: str,
    cwd: str | None,
    server_name: str,
) -> None:
    """Validate STDIO client configuration before starting process.

    Performs pre-flight checks to ensure the command exists and
    the working directory is accessible.

    Args:
        command: The command to execute
        cwd: Working directory path
        server_name: Server name for error messages

    Raises:
        ProcessError: If configuration is invalid
    """
    # Check if working directory exists and is accessible
    if cwd:
        cwd_path = Path(cwd)
        if not cwd_path.exists():
            msg = f"Working directory does not exist for server '{server_name}': {cwd}"
            raise ProcessError(msg)
        if not cwd_path.is_dir():
            msg = f"Working directory is not a directory for server '{server_name}': {cwd}"
            raise ProcessError(msg)
        if not os.access(cwd_path, os.R_OK):
            msg = f"Working directory is not readable for server '{server_name}': {cwd}"
            raise ProcessError(msg)

    # Try to validate command exists (best effort)
    try:
        # Check if command is an absolute path
        command_path = Path(command)
        if command_path.is_absolute():
            if not command_path.exists():
                logger.warning(f"Command path does not exist for server '{server_name}': {command}")
            elif not os.access(command_path, os.X_OK):
                logger.warning(f"Command is not executable for server '{server_name}': {command}")
        else:
            # For relative commands, we'll let the process creation handle it
            # since PATH resolution is complex and platform-dependent
            logger.debug(f"Command '{command}' for server '{server_name}' will be resolved via PATH")

    except (OSError, PermissionError) as e:
        logger.debug("Command access error: %s", type(e).__name__)
    except Exception as e:
        logger.warning(
            "Unexpected command validation error for server '%s' command '%s': %s", server_name, command, str(e)
        )


def validate_stdio_config(config: Any) -> list[str]:
    """Validate STDIO server configuration.

    Checks STDIO configuration for required fields and valid values.

    Args:
        config: STDIO server configuration dictionary

    Returns:
        List of validation error messages (empty if valid)

    Example:
        >>> config = {
        ...     "command": "python",
        ...     "args": ["-m", "my_server"],
        ...     "cwd": "/path/to/server"
        ... }
        >>> errors = validate_stdio_config(config)
        >>> if not errors:
        ...     print("Configuration is valid")
    """
    errors = []

    if not isinstance(config, dict):
        errors.append("STDIO config must be a dictionary")
        return errors

    # Check required fields
    command = config.get("command")
    if not command:
        errors.append("STDIO configuration requires a 'command' field")
    elif not isinstance(command, str):
        errors.append("Command must be a string")

    # Validate optional fields
    args = config.get("args")
    if args is not None and not isinstance(args, list):
        errors.append("Args must be a list of strings")
    elif args and not all(isinstance(arg, str) for arg in args):
        errors.append("All args must be strings")

    cwd = config.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        errors.append("Working directory (cwd) must be a string")

    env = config.get("env")
    if env is not None:
        if not isinstance(env, dict):
            errors.append("Environment (env) must be a dictionary")
        elif not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            errors.append("Environment variables must be string key-value pairs")

    return errors


# Custom exceptions


class ProcessError(Exception):
    """Raised when STDIO process operations fail."""


class ConfigurationError(Exception):
    """Raised when STDIO configuration is invalid."""
