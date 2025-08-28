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
from .logging import (
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
    "create_error_response",
    "extract_host_port",
    "format_exception",
    "get_logger",
    "handle_async_exception",
    "is_valid_identifier",
    "is_valid_url",
    "log_exception_details",
    "merge_json_objects",
    "normalize_name",
    "safe_json_dumps",
    "safe_json_loads",
    "safe_request_headers",
    "sanitize_filename",
    "setup_logging",
    "truncate_string",
    "validate_json_schema",
]
