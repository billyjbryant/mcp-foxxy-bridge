"""Utility functions and helpers for MCP Foxxy Bridge.

This module provides various utility functions, helpers, and common
functionality used throughout the MCP Foxxy Bridge system, including:

- Logging utilities and formatters
- HTTP request helpers
- JSON processing utilities
- String manipulation functions
- Validation helpers
- Error handling utilities

Key Components:
    - logging_utils: Enhanced logging configuration and formatters
    - http_utils: HTTP request helpers and utilities
    - json_utils: JSON processing and validation utilities
    - string_utils: String manipulation and validation functions
    - error_utils: Error handling and reporting utilities

Example:
    from mcp_foxxy_bridge.utils import setup_logging, validate_json

    setup_logging(level="DEBUG")
    data = validate_json(json_string)
"""

from .error_utils import (
    create_error_response,
    format_exception,
    handle_async_exception,
    log_exception_details,
)
from .http_utils import (
    build_url,
    extract_host_port,
    is_valid_url,
    safe_request_headers,
)
from .json_utils import (
    merge_json_objects,
    safe_json_dumps,
    safe_json_loads,
    validate_json_schema,
)
from .logging_utils import (
    configure_mcp_logging,
    create_log_formatter,
    get_logger,
    setup_logging,
)
from .string_utils import (
    is_valid_identifier,
    normalize_name,
    sanitize_filename,
    truncate_string,
)

__all__ = [
    "build_url",
    "configure_mcp_logging",
    "create_error_response",
    "create_log_formatter",
    "extract_host_port",
    # Error utilities
    "format_exception",
    "get_logger",
    "handle_async_exception",
    "is_valid_identifier",
    # HTTP utilities
    "is_valid_url",
    "log_exception_details",
    "merge_json_objects",
    # String utilities
    "normalize_name",
    "safe_json_dumps",
    # JSON utilities
    "safe_json_loads",
    "safe_request_headers",
    "sanitize_filename",
    # Logging utilities
    "setup_logging",
    "truncate_string",
    "validate_json_schema",
]
