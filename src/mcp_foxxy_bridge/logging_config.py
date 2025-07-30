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
        if hasattr(record, "name") and "servers." in record.name:
            server_name = record.name.split("servers.")[-1].split(".")[0]
            # Highlight server names in brackets
            message_text = Text.from_markup(f"[bold cyan]\\[{server_name}][/bold cyan] {message}")

        return message_text


def setup_rich_logging(*, debug: bool = False) -> logging.Logger:
    """Set up Rich-based logging configuration.

    Args:
        debug: Whether to enable debug logging level

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

    # Configure root logger
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    root_logger.addHandler(rich_handler)

    # Configure third-party loggers to use our Rich handler
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Configure uvicorn to use our Rich handler and suppress access logs in non-debug mode
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers.clear()  # Remove default handlers
    uvicorn_logger.addHandler(rich_handler)
    uvicorn_logger.setLevel(logging.INFO)
    uvicorn_logger.propagate = False  # Don't propagate to avoid duplicates

    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    uvicorn_access_logger.addHandler(rich_handler)
    uvicorn_access_logger.setLevel(logging.INFO)
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
    uvicorn_error_logger.setLevel(logging.INFO)
    uvicorn_error_logger.propagate = False

    # Set MCP library loggers to appropriate levels and use our handler
    mcp_logger = logging.getLogger("mcp")
    mcp_logger.handlers.clear()
    mcp_logger.addHandler(rich_handler)
    mcp_logger.setLevel(logging.INFO)
    mcp_logger.propagate = False

    mcp_server_logger = logging.getLogger("mcp.server")
    mcp_server_logger.handlers.clear()
    mcp_server_logger.addHandler(rich_handler)
    mcp_server_logger.setLevel(logging.INFO if debug else logging.WARNING)
    mcp_server_logger.propagate = False

    return logging.getLogger(__name__)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: The logger name

    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)
