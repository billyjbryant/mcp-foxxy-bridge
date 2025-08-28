#
# Copyright (C) 2024 Billy Bryant
# Portions copyright (C) 2024 Sergey Parfenyuk (original MIT-licensed author)
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
# MIT License attribution: Portions of this file were originally licensed
# under the MIT License by Sergey Parfenyuk (2024).
#

"""Unified logging system for MCP Foxxy Bridge.

This module consolidates all logging functionality into a single, clean interface:
- Rich console logging with automatic emoji formatting
- File logging for individual MCP servers
- Child process log capture and redirection
- Security-aware log masking for sensitive data
- Custom SUCCESS log level with logger.success() method
- Context-aware sub-facility support for server names
"""

import asyncio
import contextlib
import logging
import re
from collections.abc import AsyncIterator, Generator, Mapping
from contextvars import ContextVar, Token
from logging.handlers import RotatingFileHandler
from types import TracebackType  # noqa: TC003
from typing import cast

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

from .config_migration import get_logs_dir, get_server_logs_dir

# Add custom SUCCESS level
SUCCESS_LEVEL = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

# Context variable for server-specific logging context (used by both SERVER and OAUTH facilities)
current_server_context: ContextVar[str | None] = ContextVar("server_context", default=None)


class MCPRichHandler(RichHandler):
    """Rich handler with automatic emoji formatting and server context."""

    def __init__(self, **kwargs: object) -> None:
        if "console" not in kwargs:
            kwargs["console"] = Console(
                stderr=True,
                force_terminal=True,
                width=120,
            )

        kwargs.setdefault("show_time", True)
        kwargs.setdefault("show_level", True)
        kwargs.setdefault("show_path", False)
        kwargs.setdefault("rich_tracebacks", True)
        kwargs.setdefault("tracebacks_show_locals", False)

        super().__init__(**kwargs)  # type: ignore[arg-type]

    def get_level_text(self, record: logging.LogRecord) -> Text:
        """Get styled level text for log records."""
        level_name = record.levelname
        return Text.styled(
            f"{level_name:^7}",
            f"logging.level.{level_name.lower()}",
        )

    def render_message(self, record: logging.LogRecord, message: str) -> Text:
        """Render log message with server context highlighting."""
        formatted_message = self._add_emoji(record, message)
        message_text = Text(formatted_message)

        # Check for explicit facility first
        record_logger = logging.getLogger(record.name) if hasattr(record, "name") else None
        facility = getattr(record_logger, "_facility", None) if record_logger else None

        if facility:
            # Use explicit facility with appropriate color
            facility_colors = {
                "OAUTH": "bold orange3",
                "BRIDGE": "bold blue",
                "SERVER": "bold magenta",
                "CLIENT": "bold cyan",
                "CONFIG": "bold green",
                "SECURITY": "bold red",
                "UTILS": "bold white",
            }
            color = facility_colors.get(facility, "bold white")

            # Check for server context (applies to both SERVER and OAUTH facilities)
            sub_facility = None
            if facility in ("SERVER", "OAUTH"):
                sub_facility = current_server_context.get()

            # Format facility tag with optional sub-facility
            facility_tag = f"{facility}:{sub_facility}" if sub_facility else facility

            message_text = Text.from_markup(f"[{color}]\\[{facility_tag}][/{color}] {formatted_message}")

        elif hasattr(record, "name") and record.name:
            logger_name = record.name

            if "mcp.server." in logger_name:
                parts = logger_name.split(".")
                if len(parts) >= 3:
                    server_name = parts[2]
                    if record.levelno >= logging.ERROR:
                        server_color = "bold red"
                    elif record.levelno >= logging.WARNING:
                        server_color = "bold yellow"
                    elif record.levelno >= logging.INFO:
                        server_color = "bold green"
                    else:
                        server_color = "cyan"

                    message_text = Text.from_markup(
                        f"[{server_color}]\\[{server_name}][/{server_color}] {formatted_message}"
                    )

            elif "server_manager" in logger_name:
                message_text = Text.from_markup(f"[bold blue]\\[BRIDGE][/bold blue] {formatted_message}")

            elif "bridge_server" in logger_name:
                message_text = Text.from_markup(f"[bold magenta]\\[BRIDGE][/bold magenta] {formatted_message}")

            elif "oauth" in logger_name:
                message_text = Text.from_markup(f"[bold orange3]\\[OAUTH][/bold orange3] {formatted_message}")

        return message_text

    def _add_emoji(self, record: logging.LogRecord, message: str) -> str:
        if any(emoji in message for emoji in ["✅", "❌", "⚠️", "🔐"]):
            return message

        level_emoji = {
            SUCCESS_LEVEL: "✅",
            logging.ERROR: "❌",
            logging.WARNING: "⚠️",
            logging.CRITICAL: "❌",
        }

        if record.levelno in level_emoji:
            emoji = level_emoji[record.levelno]
            return f"{emoji} {message}"

        return message


class MCPFileLoggerManager:
    """Manages rotating file loggers for individual MCP servers."""

    def __init__(self) -> None:
        self._file_loggers: dict[str, logging.Logger] = {}
        self._file_handlers: dict[str, RotatingFileHandler] = {}

    def get_logger(self, server_name: str, log_level: str = "INFO") -> logging.Logger:
        """Get or create a file logger for a server."""
        if server_name not in self._file_loggers:
            self._create_file_logger(server_name, log_level)
        return self._file_loggers[server_name]

    def _create_file_logger(self, server_name: str, log_level: str) -> None:
        logger_name = f"mcp.server.{server_name}.file"
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        logger.propagate = False

        log_dir = get_server_logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        log_file = log_dir / f"{server_name}.log"

        handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )

        formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)

        logger.addHandler(handler)

        self._file_loggers[server_name] = logger
        self._file_handlers[server_name] = handler

    def log_message(self, server_name: str, message: str, level: int = logging.INFO) -> None:
        """Log a message to a server's file log."""
        logger = self.get_logger(server_name)
        logger.log(level, message)

    def cleanup(self) -> None:
        """Clean up all file loggers and handlers."""
        for handler in self._file_handlers.values():
            handler.close()
        self._file_loggers.clear()
        self._file_handlers.clear()


class ProcessLogHandler:
    """Captures and redirects child process output through the logging system."""

    def __init__(self, server_name: str, logger: logging.Logger) -> None:
        self.server_name = server_name
        self.logger = logger
        self._log_level_pattern = re.compile(r"\[(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\]", re.IGNORECASE)

    async def capture_output(self, process: asyncio.subprocess.Process) -> None:
        """Capture stdout and stderr from a subprocess."""
        tasks = []
        if process.stdout:
            tasks.append(asyncio.create_task(self._read_stream(process.stdout, logging.INFO)))
        if process.stderr:
            tasks.append(asyncio.create_task(self._read_stream(process.stderr, logging.WARNING)))

        # Keep references to tasks to avoid warnings
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _read_stream(self, stream: asyncio.StreamReader, default_level: int) -> None:
        while True:
            try:
                line = await stream.readline()
                if not line:
                    break

                decoded_line = line.decode("utf-8", errors="replace").rstrip()
                if decoded_line:
                    level = self._parse_log_level(decoded_line, default_level)
                    masked_line = mask_sensitive_data(decoded_line)
                    self.logger.log(level, masked_line)

            except Exception:
                break

    def _parse_log_level(self, message: str, default_level: int) -> int:
        match = self._log_level_pattern.search(message)
        if match:
            level_name = match.group(1).upper()
            if level_name in ("WARN", "WARNING"):
                return logging.WARNING
            if level_name == "ERROR":
                return logging.ERROR
            if level_name in ("CRITICAL", "FATAL"):
                return logging.CRITICAL
            if level_name == "DEBUG":
                return logging.DEBUG
            if level_name == "INFO":
                return logging.INFO
        return default_level


# Global instances
_file_logger_manager = MCPFileLoggerManager()


def setup_logging(*, debug: bool = False, quiet: bool = False) -> logging.Logger:
    """Set up the unified logging system."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    rich_handler = MCPRichHandler(
        level=logging.DEBUG if debug else logging.INFO,
        markup=True,
    )
    rich_handler.setFormatter(logging.Formatter(fmt="%(message)s", datefmt="[%X]"))

    if quiet:
        log_level = logging.WARNING
    elif debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    root_logger.setLevel(log_level)
    root_logger.addHandler(rich_handler)

    # Add file logging for main bridge process
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)  # Ensure logs directory exists
    bridge_log_file = logs_dir / "bridge.log"

    file_handler = RotatingFileHandler(
        bridge_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )

    # Use clean format for file logging (no colors/markup)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_level)
    root_logger.addHandler(file_handler)

    # Configure third-party loggers
    third_party_loggers = [
        "asyncio",
        "watchdog",
        "httpx",
        "httpcore",
        "requests",
        "urllib3",
        "boto3",
        "botocore",
        "s3transfer",
        "uvloop",
        "trio",
        "anyio",
        "pydantic",
        "jsonschema",
        "openai",
        "anthropic",
    ]
    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    # Configure uvicorn
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers.clear()
    uvicorn_logger.addHandler(rich_handler)
    uvicorn_logger.setLevel(logging.INFO if debug else logging.WARNING)
    uvicorn_logger.propagate = False

    # Configure uvicorn access logger
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    uvicorn_access_logger.addHandler(rich_handler)
    uvicorn_access_logger.setLevel(logging.INFO)
    uvicorn_access_logger.propagate = False

    # Configure uvicorn error logger
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.handlers.clear()
    uvicorn_error_logger.addHandler(rich_handler)
    uvicorn_error_logger.setLevel(logging.WARNING)
    uvicorn_error_logger.propagate = False

    # Configure MCP loggers
    mcp_logger = logging.getLogger("mcp")
    mcp_logger.handlers.clear()
    mcp_logger.addHandler(rich_handler)
    mcp_logger.setLevel(logging.WARNING)
    mcp_logger.propagate = False

    # Configure MCP server logger based on debug mode
    mcp_server_logger = logging.getLogger("mcp.server")
    mcp_server_logger.handlers.clear()
    mcp_server_logger.addHandler(rich_handler)
    mcp_server_logger.setLevel(logging.INFO if debug else logging.ERROR)
    mcp_server_logger.propagate = False

    return logging.getLogger(__name__)


def get_logger(name: str, facility: str | None = None) -> logging.Logger:
    """Get a logger with success method added and optional facility.

    Args:
        name: Logger name
        facility: Optional facility name (e.g., "OAUTH", "BRIDGE", "SERVER") for styled output
                 Sub-facility context (e.g., server names) is automatically added via context variables

    Returns:
        Logger instance with facility support
    """
    logger = logging.getLogger(name)
    _add_success_method(logger)

    # Store facility information for the render_message method
    if facility:
        logger._facility = facility  # type: ignore[attr-defined] # noqa: SLF001

    return logger


def get_file_logger(server_name: str, log_level: str = "INFO") -> logging.Logger:
    """Get a file logger for a specific server."""
    return _file_logger_manager.get_logger(server_name, log_level)


def set_server_context(server_name: str | None) -> Token[str | None]:
    """Set the server context for logging (applies to both SERVER and OAUTH facilities).

    Args:
        server_name: Name of the server or None to clear context

    Returns:
        Context token that can be used to reset the context

    Example:
        token = set_server_context("github")
        try:
            server_logger.info("Connecting")  # Shows as [SERVER:github] Connecting
            oauth_logger.info("Token refresh")  # Shows as [OAUTH:github] Token refresh
        finally:
            current_server_context.reset(token)
    """
    return current_server_context.set(server_name)


@contextlib.contextmanager
def server_context(server_name: str) -> Generator[None, None, None]:
    """Context manager for server-specific logging (applies to both SERVER and OAUTH facilities).

    Args:
        server_name: Name of the server

    Example:
        with server_context("github"):
            server_logger.info("Connecting")  # Shows as [SERVER:github] Connecting
            oauth_logger.info("Token refresh")  # Shows as [OAUTH:github] Token refresh
    """
    token = set_server_context(server_name)
    try:
        yield
    finally:
        current_server_context.reset(token)


def log_to_file(server_name: str, message: str, level: int = logging.INFO) -> None:
    """Log a message to a server's file log."""
    _file_logger_manager.log_message(server_name, message, level)


@contextlib.asynccontextmanager
async def capture_process_logs(server_name: str) -> AsyncIterator[ProcessLogHandler]:
    """Context manager for capturing child process logs."""
    logger = get_logger(f"mcp.server.{server_name}")
    handler = ProcessLogHandler(server_name, logger)
    try:
        yield handler
    finally:
        pass


def cleanup_file_loggers() -> None:
    """Clean up all file loggers."""
    _file_logger_manager.cleanup()


def mask_sensitive_data(message: str) -> str:
    """Mask sensitive data in log messages."""
    # Mask common patterns
    patterns = [
        (r'("?(?:token|password|secret|key|auth)"?\s*[:=]\s*")([^"]+)(")', r"\1***\3"),
        (r"(Bearer\s+)([A-Za-z0-9+/=]{20,})", r"\1***"),
        (r"(Authorization:\s*)(.+)", r"\1***"),
    ]

    masked = message
    for pattern, replacement in patterns:
        masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)

    return masked


def mask_authorization_header(auth_header: str) -> str:
    """Mask authorization header values while preserving structure."""
    if not auth_header or not isinstance(auth_header, str):
        return "[EMPTY_AUTH_HEADER]" if not auth_header else "[REDACTED_AUTH_HEADER]"

    auth_header = auth_header.strip()

    if not auth_header:
        return "[EMPTY_AUTH_HEADER]"

    # Split into scheme and credentials
    parts = auth_header.split(" ", 1)
    if len(parts) != 2:
        return "[REDACTED_AUTH_HEADER]"

    scheme, credentials = parts

    # For short credentials, fully redact
    if len(credentials) < 15:
        return f"{scheme} [REDACTED]"

    # For longer credentials, show partial
    prefix = credentials[:12]
    suffix = credentials[-3:]
    return f"{scheme} {prefix}...{suffix}"


def mask_oauth_tokens(tokens: dict[str, object] | None) -> dict[str, object]:
    """Mask OAuth token values while preserving structure."""
    if not tokens or not isinstance(tokens, dict):
        return {"error": "[INVALID_TOKEN_FORMAT]"}

    masked = tokens.copy()

    # Fully redact refresh tokens
    if "refresh_token" in masked:
        masked["refresh_token"] = "[REDACTED]"  # noqa: S105

    # Partially show access tokens
    if "access_token" in masked and isinstance(masked["access_token"], str):
        token = masked["access_token"]
        if len(token) >= 6:
            masked["access_token"] = f"{token[:3]}...{token[-3:]}"
        else:
            masked["access_token"] = "[REDACTED]"  # noqa: S105

    return masked


def mask_query_parameters(params: dict[str, object] | None) -> dict[str, object]:
    """Mask sensitive query parameters."""
    if not params or not isinstance(params, dict):
        return {"error": "[INVALID_PARAMS_FORMAT]"}

    masked = params.copy()

    # Fully redact authorization codes
    if "code" in masked:
        masked["code"] = "[REDACTED]"

    # Partially show state values
    if "state" in masked and isinstance(masked["state"], str):
        state = masked["state"]
        if len(state) >= 6:
            masked["state"] = f"{state[:3]}...{state[-3:]}"
        else:
            masked["state"] = "[REDACTED]"

    return masked


def mask_authentication_config(config: dict[str, object] | None) -> dict[str, object]:
    """Mask authentication configuration values."""
    if not config or not isinstance(config, dict):
        return {"error": "[INVALID_AUTH_CONFIG]"}

    masked = config.copy()

    # Fully redact sensitive fields
    sensitive_fields = ["password", "api_key", "secret", "token", "key"]
    for field in sensitive_fields:
        if field in masked:
            masked[field] = "[REDACTED]"

    return masked


def redact_url_credentials(url: str | int | None) -> str:
    """Redact credentials from URLs."""
    if not isinstance(url, str):
        return "[INVALID_URL]"

    # Replace user:pass@ with [REDACTED]@
    pattern = r"(https?://)([^@/]+@)(.+)"
    return re.sub(pattern, r"\1[REDACTED]@\3", url)


def safe_log_headers(headers: dict[str, object] | None) -> dict[str, object]:
    """Safely log HTTP headers by redacting sensitive ones."""
    if not headers or not isinstance(headers, dict):
        return {"error": "[INVALID_HEADERS]"}

    masked = headers.copy()

    # Redact sensitive headers
    sensitive_patterns = [r".*auth.*", r".*token.*", r".*key.*", r".*secret.*"]

    for header_name in list(masked.keys()):
        for pattern in sensitive_patterns:
            if re.match(pattern, header_name, re.IGNORECASE):
                masked[header_name] = "[REDACTED]"
                break

    return masked


def safe_log_server_name(server_name: str | None, show_partial: bool = False) -> str:
    """Safely log server names with optional partial visibility."""
    if server_name is None or not isinstance(server_name, str):
        return "[INVALID_SERVER_NAME]"

    server_name = server_name.strip()
    if not server_name:
        return "[EMPTY_SERVER_NAME]"

    if not show_partial:
        return "[SERVER_NAME]"

    # For partial visibility, show first 3 and last 3 chars
    if len(server_name) >= 8:
        return f"{server_name[:3]}...{server_name[-3:]}"
    return "[SERVER_NAME]"


def _add_success_method(logger: logging.Logger) -> None:
    """Add success method to logger."""
    if not hasattr(logger, "success"):

        def success(message: str, *args: object, **kwargs: object) -> None:
            # Extract and type-cast known kwargs for logger.log()

            exc_info = cast(
                (
                    "bool | tuple[type[BaseException], BaseException, TracebackType | None] | "
                    "tuple[None, None, None] | BaseException | None"
                ),
                kwargs.get("exc_info"),
            )
            stack_info = cast("bool", kwargs.get("stack_info", False))
            stacklevel = cast("int", kwargs.get("stacklevel", 1))
            extra = cast("Mapping[str, object] | None", kwargs.get("extra"))

            logger.log(
                SUCCESS_LEVEL,
                message,
                *args,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel,
                extra=extra,
            )

        logger.success = success  # type: ignore[attr-defined]


# Monkey patch Logger class
def _patch_logger_class() -> None:
    """Add success method to all loggers."""

    def success(self: logging.Logger, message: str, *args: object, **kwargs: object) -> None:
        # Extract and type-cast known kwargs for logger.log()

        exc_info = cast(
            (
                "bool | tuple[type[BaseException], BaseException, TracebackType | None] | "
                "tuple[None, None, None] | BaseException | None"
            ),
            kwargs.get("exc_info"),
        )
        stack_info = cast("bool", kwargs.get("stack_info", False))
        stacklevel = cast("int", kwargs.get("stacklevel", 1))
        extra = cast("Mapping[str, object] | None", kwargs.get("extra"))

        self.log(
            SUCCESS_LEVEL, message, *args, exc_info=exc_info, stack_info=stack_info, stacklevel=stacklevel, extra=extra
        )

    if not hasattr(logging.Logger, "success"):
        logging.Logger.success = success  # type: ignore[attr-defined]


# Apply patch on import
_patch_logger_class()
