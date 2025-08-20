#
# MCP Foxxy Bridge - Logging Utilities
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
"""Logging Utilities for MCP Foxxy Bridge.

This module provides comprehensive logging configuration and utilities
for the MCP Foxxy Bridge system, including structured logging, custom
formatters, and MCP-specific logging configuration.

Key Features:
    - Structured JSON logging support
    - Color-coded console output
    - MCP protocol-specific logging
    - Per-server logging configuration
    - Log level management
    - Custom log formatters

Example:
    Basic logging setup:

    >>> setup_logging(level="INFO")
    >>> logger = get_logger("my_module")
    >>> logger.info("Application started")

    MCP server logging:

    >>> configure_mcp_logging("server_name", level="DEBUG")
    >>> logger = get_logger("mcp.server_name")
    >>> logger.debug("MCP message received")
"""

import json
import logging
import logging.handlers
import re
import sys
from collections.abc import MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from re import Match
from typing import Any


# ANSI color codes for console output
class LogColors:
    """ANSI color codes for colorized console logging."""

    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Level colors
    DEBUG = "\033[36m"  # Cyan
    INFO = "\033[32m"  # Green
    WARNING = "\033[33m"  # Yellow
    ERROR = "\033[31m"  # Red
    CRITICAL = "\033[35m"  # Magenta

    # Component colors
    TIMESTAMP = "\033[90m"  # Dark gray
    LOGGER = "\033[94m"  # Light blue
    MESSAGE = "\033[97m"  # White


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color coding to console log output.

    This formatter provides color-coded log levels and structured
    formatting for improved readability in console output.

    Example:
        >>> formatter = ColoredFormatter()
        >>> handler = logging.StreamHandler()
        >>> handler.setFormatter(formatter)
    """

    def __init__(self, include_timestamp: bool = True, include_logger: bool = True) -> None:
        """Initialize colored formatter.

        Args:
            include_timestamp: Whether to include timestamp in output
            include_logger: Whether to include logger name in output
        """
        self.include_timestamp = include_timestamp
        self.include_logger = include_logger
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        # Get level color
        level_colors = {
            "DEBUG": LogColors.DEBUG,
            "INFO": LogColors.INFO,
            "WARNING": LogColors.WARNING,
            "ERROR": LogColors.ERROR,
            "CRITICAL": LogColors.CRITICAL,
        }
        level_color = level_colors.get(record.levelname, LogColors.RESET)

        # Build formatted message parts
        parts = []

        if self.include_timestamp:
            timestamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S.%f")[:-3]
            parts.append(f"{LogColors.TIMESTAMP}{timestamp}{LogColors.RESET}")

        # Colored level name
        parts.append(f"{level_color}{LogColors.BOLD}{record.levelname:<8}{LogColors.RESET}")

        if self.include_logger:
            parts.append(f"{LogColors.LOGGER}{record.name}{LogColors.RESET}")

        # Message
        message = record.getMessage()
        parts.append(f"{LogColors.MESSAGE}{message}{LogColors.RESET}")

        # Join parts
        formatted = " ".join(parts)

        # Add exception info if present
        if record.exc_info:
            formatted += f"\n{LogColors.ERROR}{self.formatException(record.exc_info)}{LogColors.RESET}"

        return formatted


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    This formatter outputs log records as JSON objects, making them
    suitable for log aggregation systems and structured analysis.

    Example:
        >>> formatter = JSONFormatter()
        >>> handler = logging.FileHandler("app.log")
        >>> handler.setFormatter(formatter)
    """

    def __init__(self, include_extra: bool = True) -> None:
        """Initialize JSON formatter.

        Args:
            include_extra: Whether to include extra fields from log record
        """
        self.include_extra = include_extra
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add process/thread info
        if record.processName != "MainProcess":
            log_obj["process"] = record.processName
        if record.threadName != "MainThread":
            log_obj["thread"] = record.threadName

        # Add exception info if present
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is not None:
                log_obj["exception"] = {
                    "type": exc_type.__name__,
                    "message": str(record.exc_info[1]),
                    "traceback": self.formatException(record.exc_info),
                }
            else:
                log_obj["exception"] = {
                    "type": "Unknown",
                    "message": str(record.exc_info[1]),
                    "traceback": self.formatException(record.exc_info),
                }

        # Add extra fields
        if self.include_extra:
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in log_obj and not key.startswith("_"):
                    # Skip standard logging fields
                    if key not in (
                        "name",
                        "msg",
                        "args",
                        "levelname",
                        "levelno",
                        "pathname",
                        "filename",
                        "module",
                        "lineno",
                        "funcName",
                        "created",
                        "msecs",
                        "relativeCreated",
                        "thread",
                        "threadName",
                        "processName",
                        "process",
                        "getMessage",
                        "exc_info",
                        "exc_text",
                        "stack_info",
                    ):
                        extra_fields[key] = value

            if extra_fields:
                log_obj["extra"] = extra_fields

        return json.dumps(log_obj, default=str)


class MCPLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    """Logger adapter that adds MCP-specific context to log records.

    This adapter automatically adds server name and other MCP-specific
    information to log records for better traceability.

    Example:
        >>> logger = logging.getLogger("mcp")
        >>> adapter = MCPLoggerAdapter(logger, {"server": "filesystem"})
        >>> adapter.info("Tool call received")
    """

    def __init__(self, logger: logging.Logger, extra: dict[str, Any]) -> None:
        """Initialize MCP logger adapter.

        Args:
            logger: Base logger instance
            extra: Extra context to add to log records
        """
        super().__init__(logger, extra)

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        """Process log record to add MCP context."""
        # Add server context to extra fields
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"].update(self.extra)

        return msg, kwargs


# Main logging configuration functions


def setup_logging(
    level: str | int = "INFO",
    format_type: str = "colored",
    log_file: str | None = None,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> None:
    """Set up logging configuration for the application.

    Configures both console and file logging with appropriate formatters
    and handlers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Formatter type ("colored", "json", "simple")
        log_file: Optional path to log file
        max_file_size: Maximum size of log file before rotation
        backup_count: Number of backup log files to keep

    Example:
        >>> setup_logging(level="DEBUG", format_type="colored")
        >>> setup_logging(level="INFO", log_file="app.log", format_type="json")
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO) if isinstance(level, str) else level

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    # Set console formatter
    if format_type == "colored" and sys.stdout.isatty():
        console_formatter: logging.Formatter = ColoredFormatter()
    elif format_type == "json":
        console_formatter = JSONFormatter()
    else:
        console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Create file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=max_file_size, backupCount=backup_count)
        file_handler.setLevel(numeric_level)

        # Use JSON formatter for file output
        file_formatter = JSONFormatter()
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Set up some default logger levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str, server_name: str | None = None) -> logging.Logger | MCPLoggerAdapter:
    """Get a logger instance with optional MCP server context.

    Args:
        name: Logger name
        server_name: Optional MCP server name for context

    Returns:
        Logger instance or MCPLoggerAdapter if server_name provided

    Example:
        >>> logger = get_logger("my_module")
        >>> mcp_logger = get_logger("mcp.tools", server_name="filesystem")
    """
    logger = logging.getLogger(name)

    if server_name:
        return MCPLoggerAdapter(logger, {"server": server_name})

    return logger


def configure_mcp_logging(server_name: str, level: str | int = "QUIET", namespace: str | None = None) -> None:
    """Configure logging for a specific MCP server.

    Sets up logger configuration for an individual MCP server with
    appropriate log levels and context using Rich formatting.

    Args:
        server_name: Name of the MCP server
        level: Logging level for this server
        namespace: Optional namespace prefix

    Example:
        >>> configure_mcp_logging("filesystem", level="DEBUG")
        >>> configure_mcp_logging("atlassian", level="INFO", namespace="mcp")
    """
    # Convert string level to logging constant
    if isinstance(level, str):
        if level.upper() == "QUIET":
            numeric_level = logging.CRITICAL + 1  # Higher than any real log level
        else:
            numeric_level = getattr(logging, level.upper(), logging.ERROR)
    else:
        numeric_level = level

    # Create logger name
    logger_name = f"{namespace}.{server_name}" if namespace else f"mcp.{server_name}"

    # Configure logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(numeric_level)

    # Ensure the logger uses the rich handler from root logger
    if not logger.handlers:
        root_logger = logging.getLogger()
        if root_logger.handlers:
            # Copy the rich handler from root logger
            for handler in root_logger.handlers:
                logger.addHandler(handler)

    # Set propagation - don't propagate to avoid duplicate messages since we're using root handlers
    logger.propagate = False


def create_log_formatter(format_type: str = "colored") -> logging.Formatter:
    """Create a log formatter of the specified type.

    Args:
        format_type: Type of formatter ("colored", "json", "simple")

    Returns:
        Configured formatter instance

    Example:
        >>> formatter = create_log_formatter("json")
        >>> handler.setFormatter(formatter)
    """
    if format_type == "colored":
        return ColoredFormatter()
    if format_type == "json":
        return JSONFormatter()
    return logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def log_mcp_message(
    logger: logging.Logger,
    direction: str,
    message_type: str,
    content: dict[str, Any],
    server_name: str | None = None,
) -> None:
    """Log an MCP protocol message with structured information.

    Args:
        logger: Logger instance to use
        direction: Message direction ("sent" or "received")
        message_type: Type of MCP message
        content: Message content
        server_name: Optional server name for context

    Example:
        >>> log_mcp_message(
        ...     logger, "received", "tools/list", {"tools": [...]},
        ...     server_name="filesystem"
        ... )
    """
    extra = {
        "mcp_direction": direction,
        "mcp_message_type": message_type,
        "mcp_server": server_name,
    }

    message = f"MCP {direction}: {message_type}"
    if server_name:
        message += f" (server: {server_name})"

    logger.debug(message, extra=extra)


def set_verbose_logging(enabled: bool = True) -> None:
    """Enable or disable verbose logging for debugging.

    Args:
        enabled: Whether to enable verbose logging

    Example:
        >>> set_verbose_logging(True)  # Enable debug logging
        >>> set_verbose_logging(False)  # Restore normal logging
    """
    if enabled:
        logging.getLogger().setLevel(logging.DEBUG)
        # Enable debug logging for key modules
        logging.getLogger("mcp_foxxy_bridge").setLevel(logging.DEBUG)
        logging.getLogger("mcp").setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
        # Restore default levels
        logging.getLogger("mcp_foxxy_bridge").setLevel(logging.INFO)
        logging.getLogger("mcp").setLevel(logging.INFO)


# Secure Logging Utilities for Sensitive Data Protection


def mask_authorization_header(header_value: str, prefix_chars: int = 12, suffix_chars: int = 4) -> str:
    """Mask an Authorization header value for safe logging.

    Shows the token type and first/last few characters while masking the sensitive middle portion.

    Args:
        header_value: The authorization header value (e.g., "Bearer abc123...")
        prefix_chars: Number of characters to show at the beginning of the token
        suffix_chars: Number of characters to show at the end of the token

    Returns:
        Masked header value safe for logging

    Example:
        >>> mask_authorization_header("Bearer abc123def456ghi789")
        'Bearer abc123...i789'
        >>> mask_authorization_header("Basic dXNlcjpwYXNz")
        'Basic dXNlcjpwY...YXNz'
    """
    if not header_value or not isinstance(header_value, str):
        return "[EMPTY_AUTH_HEADER]"

    # Split into scheme and credentials
    parts = header_value.split(" ", 1)
    if len(parts) != 2:
        # Not a standard authorization header format
        return "[REDACTED_AUTH_HEADER]"

    scheme, credentials = parts

    # If credentials are too short, just show scheme and indicate redacted
    if len(credentials) <= (prefix_chars + suffix_chars):
        return f"{scheme} [REDACTED]"

    # Create masked version
    prefix = credentials[:prefix_chars] if prefix_chars > 0 else ""
    suffix = credentials[-suffix_chars:] if suffix_chars > 0 else ""
    return f"{scheme} {prefix}...{suffix}" if prefix or suffix else f"{scheme} [REDACTED]"


def mask_oauth_tokens(tokens_info: Any) -> dict[str, Any]:
    """Mask sensitive OAuth token information for safe logging.

    Args:
        tokens_info: Dictionary containing OAuth token information

    Returns:
        Dictionary with sensitive values masked

    Example:
        >>> tokens = {"access_token": "abc123", "refresh_token": "def456", "scope": "read write"}
        >>> mask_oauth_tokens(tokens)
        {'access_token': 'abc...123', 'refresh_token': '[REDACTED]', 'scope': 'read write'}
    """
    if not isinstance(tokens_info, dict):
        return {"error": "[INVALID_TOKEN_FORMAT]"}

    masked = {}
    sensitive_fields = {
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "code",
        "authorization_code",
        "password",
        "client_assertion",
    }

    for key, value in tokens_info.items():
        if key.lower() in sensitive_fields:
            if isinstance(value, str) and len(value) > 8:
                # Show first 3 and last 3 characters for access tokens, fully redact others
                if key.lower() == "access_token":
                    masked[key] = f"{value[:3]}...{value[-3:]}"
                else:
                    masked[key] = "[REDACTED]"
            else:
                masked[key] = "[REDACTED]"
        else:
            # Non-sensitive fields like expires_in, token_type, scope
            masked[key] = value

    return masked


def mask_query_parameters(params: Any) -> dict[str, Any]:
    """Mask sensitive query parameters for safe logging.

    Args:
        params: Dictionary of query parameters

    Returns:
        Dictionary with sensitive parameters masked

    Example:
        >>> params = {"code": "auth123", "state": "state456", "error": "access_denied"}
        >>> mask_query_parameters(params)
        {'code': '[REDACTED]', 'state': 'sta...456', 'error': 'access_denied'}
    """
    if not isinstance(params, dict):
        return {"error": "[INVALID_PARAMS_FORMAT]"}

    masked = {}
    highly_sensitive = {"code", "client_secret", "password", "access_token", "refresh_token"}
    moderately_sensitive = {"state", "code_verifier", "nonce"}

    for key, value in params.items():
        key_lower = key.lower()
        if key_lower in highly_sensitive:
            masked[key] = "[REDACTED]"
        elif key_lower in moderately_sensitive and isinstance(value, str) and len(value) > 6:
            # Show partial for moderately sensitive (useful for debugging state/nonce)
            masked[key] = f"{value[:3]}...{value[-3:]}"
        else:
            # Non-sensitive parameters like error, error_description, scope
            masked[key] = value

    return masked


def mask_authentication_config(auth_config: Any) -> dict[str, Any]:
    """Mask sensitive authentication configuration for safe logging.

    Args:
        auth_config: Authentication configuration dictionary

    Returns:
        Dictionary with sensitive values masked

    Example:
        >>> config = {"type": "basic", "username": "user", "password": "secret123"}
        >>> mask_authentication_config(config)
        {'type': 'basic', 'username': 'user', 'password': '[REDACTED]'}
    """
    if not isinstance(auth_config, dict):
        return {"error": "[INVALID_AUTH_CONFIG]"}

    masked = {}
    sensitive_fields = {"password", "token", "key", "secret", "client_secret", "api_key"}

    for field, value in auth_config.items():
        if field.lower() in sensitive_fields or "password" in field.lower() or "secret" in field.lower():
            masked[field] = "[REDACTED]"
        else:
            masked[field] = value

    return masked


def redact_url_credentials(url: Any) -> str:
    """Redact credentials from URLs for safe logging.

    Args:
        url: URL that may contain embedded credentials

    Returns:
        URL with credentials redacted

    Example:
        >>> redact_url_credentials("https://user:pass@example.com/path")
        'https://[REDACTED]@example.com/path'
    """
    if not isinstance(url, str):
        return "[INVALID_URL]"

    # Pattern to match URLs with embedded credentials
    pattern = r"(https?://)([^:]+):([^@]+)@"

    def replace_creds(match: Match[str]) -> str:
        return f"{match.group(1)}[REDACTED]@"

    return re.sub(pattern, replace_creds, url)


def safe_log_headers(headers: Any) -> dict[str, str]:
    """Create a safe version of HTTP headers for logging.

    Args:
        headers: Dictionary of HTTP headers

    Returns:
        Dictionary with sensitive headers masked

    Example:
        >>> headers = {"Authorization": "Bearer abc123", "User-Agent": "MyApp", "X-API-Key": "secret"}
        >>> safe_log_headers(headers)
        {'Authorization': '[REDACTED]', 'User-Agent': 'MyApp', 'X-API-Key': '[REDACTED]'}
    """
    if not isinstance(headers, dict):
        return {"error": "[INVALID_HEADERS]"}

    safe_headers = {}
    sensitive_header_patterns = [
        r"authorization",
        r".*-key",
        r".*-token",
        r".*-secret",
        r"cookie",
        r"set-cookie",
        r"proxy-authorization",
    ]

    for name, value in headers.items():
        name_lower = name.lower()
        is_sensitive = any(re.match(pattern, name_lower) for pattern in sensitive_header_patterns)

        if is_sensitive:
            safe_headers[name] = "[REDACTED]"
        else:
            safe_headers[name] = str(value) if value is not None else ""

    return safe_headers


def safe_log_server_name(server_name: Any, show_partial: bool = False) -> str:
    """Create a safe version of server name for logging.

    Args:
        server_name: Server name that might contain sensitive data
        show_partial: Whether to show partial server name for debugging

    Returns:
        Safe server name for logging

    Example:
        >>> safe_log_server_name("oauth-server-production")
        '[SERVER_NAME]'
        >>> safe_log_server_name("oauth-server-production", show_partial=True)
        'oau...-ion'
    """
    if not isinstance(server_name, str):
        return "[INVALID_SERVER_NAME]"

    if not server_name.strip():
        return "[EMPTY_SERVER_NAME]"

    if show_partial and len(server_name) > 8:
        # Show first 3 and last 3 characters for debugging
        return f"{server_name[:3]}...{server_name[-3:]}"

    return "[SERVER_NAME]"
