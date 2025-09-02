#
# MCP Foxxy Bridge - Error Handling Utilities
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
"""Error Handling Utilities for MCP Foxxy Bridge.

This module provides utilities for exception handling, error formatting,
and error response creation.
"""

import asyncio
import traceback
from typing import Any

from mcp_foxxy_bridge.utils.logging import get_logger

logger = get_logger(__name__, facility="UTILS")


def format_exception(exc: Exception, include_traceback: bool = True) -> str:
    """Format exception for logging or display.

    Args:
        exc: Exception to format
        include_traceback: Whether to include full traceback

    Returns:
        Formatted exception string
    """
    if include_traceback:
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return f"{type(exc).__name__}: {exc}"


def log_exception_details(exc: Exception, context: str | None = None) -> None:
    """Log detailed exception information.

    Args:
        exc: Exception to log
        context: Optional context description
    """
    if context:
        logger.exception(f"Exception in {context}: {exc}")
    else:
        logger.exception(f"Exception occurred: {exc}")


def create_error_response(error: str, code: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create standardized error response.

    Args:
        error: Error message
        code: Optional error code
        details: Optional additional details

    Returns:
        Error response dictionary
    """
    response: dict[str, Any] = {
        "error": error,
        "timestamp": str(asyncio.get_running_loop().time() if asyncio.get_event_loop().is_running() else 0),
    }

    if code:
        response["code"] = code

    if details:
        response["details"] = details

    return response


async def handle_async_exception(exc: Exception, context: str | None = None) -> None:
    """Handle async exceptions with proper logging.

    Args:
        exc: Exception to handle
        context: Optional context description
    """
    log_exception_details(exc, context)

    # Could add additional async error handling here
    # like sending to error reporting service, etc.
