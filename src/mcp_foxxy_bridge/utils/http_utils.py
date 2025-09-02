#
# MCP Foxxy Bridge - HTTP Utilities
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
"""HTTP Utilities for MCP Foxxy Bridge.

This module provides HTTP-related utility functions for URL validation,
header management, and request handling.
"""

import urllib.parse

from mcp_foxxy_bridge.utils.logging import get_logger

logger = get_logger(__name__, facility="UTILS")


def is_valid_url(url: str) -> bool:
    """Check if URL is valid.

    Args:
        url: URL to validate

    Returns:
        True if URL is valid, False otherwise
    """
    try:
        parsed = urllib.parse.urlparse(url)
        return all([parsed.scheme, parsed.netloc])
    except (ValueError, TypeError) as e:
        logger.debug("URL validation error: %s", e)
        return False
    except Exception as e:
        logger.warning("Unexpected URL validation error: %s", str(e))
        return False


def extract_host_port(url: str) -> tuple[str | None, int | None]:
    """Extract host and port from URL.

    Args:
        url: URL to parse

    Returns:
        Tuple of (host, port)
    """
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.hostname, parsed.port
    except (ValueError, TypeError) as e:
        logger.debug("URL parsing error: %s", e)
        return None, None
    except Exception as e:
        logger.warning("Unexpected URL parsing error: %s", str(e))
        return None, None


def build_url(base_url: str, path: str = "", params: dict[str, str] | None = None) -> str:
    """Build URL from components.

    Args:
        base_url: Base URL
        path: Path to append
        params: Query parameters

    Returns:
        Complete URL string
    """
    url = base_url.rstrip("/") + "/" + path.lstrip("/")

    if params:
        query_string = urllib.parse.urlencode(params)
        url += "?" + query_string

    return url


def safe_request_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Sanitize request headers.

    Args:
        headers: Headers dictionary

    Returns:
        Sanitized headers dictionary
    """
    if not headers:
        return {}

    # Remove sensitive headers from logging
    safe_headers = {}
    for key, value in headers.items():
        if key.lower() in ("authorization", "cookie", "x-api-key"):
            safe_headers[key] = "[REDACTED]"
        else:
            safe_headers[key] = value

    return safe_headers
