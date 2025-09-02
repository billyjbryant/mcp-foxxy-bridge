#
# MCP Foxxy Bridge - JSON Utilities
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
"""JSON Utilities for MCP Foxxy Bridge.

This module provides JSON processing utilities for safe parsing,
validation, and manipulation.
"""

import json
from typing import Any

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from mcp_foxxy_bridge.utils.logging import get_logger

logger = get_logger(__name__, facility="UTILS")


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """Safely load JSON string.

    Args:
        json_str: JSON string to parse
        default: Default value if parsing fails

    Returns:
        Parsed JSON data or default value
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Failed to parse JSON: {json_str[:100]}...")
        return default


def safe_json_dumps(data: Any, default: Any = None, **kwargs: Any) -> str | None:
    """Safely dump data to JSON string.

    Args:
        data: Data to serialize
        default: Default JSON encoder
        **kwargs: Additional json.dumps arguments

    Returns:
        JSON string or None if serialization fails
    """
    try:
        return json.dumps(data, default=default, **kwargs)
    except (TypeError, ValueError):
        logger.warning("Failed to serialize data to JSON")
        return None


def validate_json_schema(data: Any, schema: dict[str, Any]) -> bool:
    """Validate JSON data against schema.

    Args:
        data: Data to validate
        schema: JSON schema

    Returns:
        True if valid, False otherwise
    """
    if not JSONSCHEMA_AVAILABLE:
        logger.warning("jsonschema not available, skipping validation")
        return True

    try:
        jsonschema.validate(data, schema)  # type: ignore[no-untyped-call]
        return True
    except jsonschema.ValidationError:
        return False


def merge_json_objects(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge two JSON objects.

    Args:
        base: Base object
        override: Override object

    Returns:
        Merged object
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_json_objects(result[key], value)
        else:
            result[key] = value

    return result
