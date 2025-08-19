#
# MCP Foxxy Bridge - Enhanced Logging Configuration
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
"""Enhanced logging configuration using Rich for beautiful console output."""

import logging

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text


class MCPRichHandler(RichHandler):
    """Custom Rich handler for MCP Foxxy Bridge with enhanced formatting."""

    def __init__(self, **kwargs: object) -> None:
        """Initialize the MCP Rich handler with custom settings."""
        # Create a console with custom settings if not provided
        if "console" not in kwargs:
            kwargs["console"] = Console(
                stderr=True,  # Use stderr for logging output
                force_terminal=True,  # Force color output even when redirected
                width=120,  # Set a reasonable width
            )

        # Set default values for Rich handler options
        kwargs.setdefault("show_time", True)
        kwargs.setdefault("show_level", True)
        kwargs.setdefault("show_path", False)  # Don't show full file paths
        kwargs.setdefault("rich_tracebacks", True)
        kwargs.setdefault("tracebacks_show_locals", False)  # Don't show locals

        super().__init__(**kwargs)  # type: ignore[arg-type]

    def get_level_text(self, record: logging.LogRecord) -> Text:
        """Get level text with custom colors and styling."""
        level_name = record.levelname
        return Text.styled(
            f"{level_name:^7}",  # Center the level name in 7 characters
            f"logging.level.{level_name.lower()}",
        )

    def render_message(self, record: logging.LogRecord, message: str) -> Text:
        """Render the log message with custom formatting."""
        # Create message text
        message_text = Text(message)

        # Add server name highlighting for MCP server logs
        if hasattr(record, "name") and record.name:
            logger_name = record.name

            # Handle MCP server logs with improved formatting
            if "mcp.server." in logger_name:
                # Extract server name from logger name like "mcp.server.servername" or "mcp.server.servername.file"
                parts = logger_name.split(".")
                if len(parts) >= 3:
                    server_name = parts[2]  # server name is the 3rd part
                    # Use different colors for different log levels
                    if record.levelno >= logging.ERROR:
                        server_color = "bold red"
                    elif record.levelno >= logging.WARNING:
                        server_color = "bold yellow"
                    elif record.levelno >= logging.INFO:
                        server_color = "bold green"
                    else:
                        server_color = "cyan"

                    message_text = Text.from_markup(f"[{server_color}]\\[{server_name}][/{server_color}] {message}")

            # Handle general server manager logs
            elif "server_manager" in logger_name:
                message_text = Text.from_markup(f"[bold blue]\\[BRIDGE][/bold blue] {message}")

            # Handle bridge server logs
            elif "bridge_server" in logger_name:
                message_text = Text.from_markup(f"[bold magenta]\\[BRIDGE][/bold magenta] {message}")

        return message_text


def setup_rich_logging(*, debug: bool = False, quiet: bool = False) -> logging.Logger:
    """Set up Rich-based logging configuration.

    Args:
        debug: Whether to enable debug logging level
        quiet: Whether to enable quiet mode (less startup verbosity)

    Returns:
        The configured logger for the main module
    """
    # Clear any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create and configure the Rich handler
    rich_handler = MCPRichHandler(
        level=logging.DEBUG if debug else logging.INFO,
        markup=True,  # Enable Rich markup in log messages
    )

    # Set the format for the Rich handler
    rich_handler.setFormatter(logging.Formatter(fmt="%(message)s", datefmt="[%X]"))

    # Configure root logger - use WARNING for quiet mode
    if quiet:
        log_level = logging.WARNING
    elif debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    root_logger.setLevel(log_level)
    root_logger.addHandler(rich_handler)

    # Configure third-party loggers to reduce verbosity
    logging.getLogger("asyncio").setLevel(logging.ERROR)
    logging.getLogger("watchdog").setLevel(logging.ERROR)
    logging.getLogger("watchdog.observers").setLevel(logging.ERROR)
    logging.getLogger("watchdog.events").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("boto3").setLevel(logging.ERROR)
    logging.getLogger("botocore").setLevel(logging.ERROR)
    logging.getLogger("s3transfer").setLevel(logging.ERROR)

    # Reduce verbosity of common MCP-related third-party libraries
    logging.getLogger("uvloop").setLevel(logging.ERROR)
    logging.getLogger("trio").setLevel(logging.ERROR)
    logging.getLogger("anyio").setLevel(logging.ERROR)
    logging.getLogger("pydantic").setLevel(logging.ERROR)
    logging.getLogger("jsonschema").setLevel(logging.ERROR)
    logging.getLogger("openai").setLevel(logging.ERROR)
    logging.getLogger("anthropic").setLevel(logging.ERROR)

    # Configure uvicorn to be much quieter unless debug mode
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers.clear()  # Remove default handlers
    uvicorn_logger.addHandler(rich_handler)
    uvicorn_logger.setLevel(logging.INFO if debug else logging.WARNING)
    uvicorn_logger.propagate = False  # Don't propagate to avoid duplicates

    # Suppress access logs entirely in non-debug mode
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    if debug:
        uvicorn_access_logger.addHandler(rich_handler)
        uvicorn_access_logger.setLevel(logging.INFO)
    else:
        uvicorn_access_logger.setLevel(logging.ERROR)  # Suppress access logs
    uvicorn_access_logger.propagate = False

    # Create a custom formatter for uvicorn access logs to match our style
    class UvicornAccessFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            # Extract client info and request details from uvicorn's access log
            min_args_count = 3
            if (
                hasattr(record, "args")
                and record.args
                and isinstance(record.args, tuple)
                and len(record.args) >= min_args_count
            ):
                client = record.args[0]
                method_path = record.args[1]
                status = record.args[2]
                return f'{client} - "{method_path}" {status}'
            return super().format(record)

    # Apply custom formatter to access logger
    for handler in uvicorn_access_logger.handlers:
        handler.setFormatter(UvicornAccessFormatter())

    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.handlers.clear()
    uvicorn_error_logger.addHandler(rich_handler)
    uvicorn_error_logger.setLevel(logging.WARNING)
    uvicorn_error_logger.propagate = False

    # Set MCP library loggers to appropriate levels and use our handler
    mcp_logger = logging.getLogger("mcp")
    mcp_logger.handlers.clear()
    mcp_logger.addHandler(rich_handler)
    mcp_logger.setLevel(logging.WARNING)  # Only show warnings and errors from MCP lib
    mcp_logger.propagate = False

    # MCP server loggers should respect individual server log levels
    # This will be overridden by individual server configurations
    mcp_server_logger = logging.getLogger("mcp.server")
    mcp_server_logger.handlers.clear()
    mcp_server_logger.addHandler(rich_handler)
    mcp_server_logger.setLevel(logging.ERROR if not debug else logging.INFO)  # Suppress most MCP server logs
    mcp_server_logger.propagate = False

    # Also suppress the lowlevel server logs that generate "Processing request" messages
    mcp_lowlevel_logger = logging.getLogger("mcp.server.lowlevel")
    mcp_lowlevel_logger.handlers.clear()
    mcp_lowlevel_logger.addHandler(rich_handler)
    mcp_lowlevel_logger.setLevel(logging.ERROR)  # Only show errors from lowlevel
    mcp_lowlevel_logger.propagate = False

    # Suppress common MCP server loggers that are very chatty
    for logger_name in [
        "mcp.server.lowlevel.server",
        "mcp.server.stdio",
        "mcp.server.session",
        "fastmcp.server",
        "fastmcp",
    ]:
        chatty_logger = logging.getLogger(logger_name)
        chatty_logger.handlers.clear()
        chatty_logger.addHandler(rich_handler)
        chatty_logger.setLevel(logging.ERROR)
        chatty_logger.propagate = False

    return logging.getLogger(__name__)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: The logger name

    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)
