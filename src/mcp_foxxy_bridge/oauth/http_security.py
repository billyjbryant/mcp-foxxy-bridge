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

"""Secure HTTP client configuration for OAuth operations."""

from typing import Any

import httpx

from .config import OAUTH_USER_AGENT

# Security-hardened timeout configuration
DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0,  # Connection timeout
    read=30.0,  # Read timeout
    write=10.0,  # Write timeout
    pool=5.0,  # Pool acquisition timeout
)

# Connection limits to prevent resource exhaustion
DEFAULT_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=100, keepalive_expiry=30.0)

# Default security headers
DEFAULT_HEADERS = {
    "User-Agent": OAUTH_USER_AGENT,
    # Prevent MIME type sniffing
    "X-Content-Type-Options": "nosniff",
    # Prevent cross-site scripting
    "X-XSS-Protection": "1; mode=block",
    # Prevent framing
    "X-Frame-Options": "DENY",
}


def create_secure_client(follow_redirects: bool = True) -> httpx.Client:
    """Create a security-hardened synchronous HTTP client.

    Args:
        follow_redirects: Whether to automatically follow redirects (default: True for OAuth compatibility)

    Returns:
        httpx.Client configured with security best practices
    """
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        limits=DEFAULT_LIMITS,
        headers=DEFAULT_HEADERS,
        verify=True,  # Always verify SSL certificates
        trust_env=False,  # Don't trust environment proxy settings
        follow_redirects=follow_redirects,  # Configurable redirect handling
        http2=True,  # Enable HTTP/2 support
    )


def create_secure_async_client(follow_redirects: bool = True) -> httpx.AsyncClient:
    """Create a security-hardened asynchronous HTTP client.

    Args:
        follow_redirects: Whether to automatically follow redirects (default: True for OAuth compatibility)

    Returns:
        httpx.AsyncClient configured with security best practices
    """
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        limits=DEFAULT_LIMITS,
        headers=DEFAULT_HEADERS,
        verify=True,  # Always verify SSL certificates
        trust_env=False,  # Don't trust environment proxy settings
        follow_redirects=follow_redirects,  # Configurable redirect handling
        http2=True,  # Enable HTTP/2 support
    )


def create_localhost_client(follow_redirects: bool = True) -> httpx.AsyncClient:
    """Create an HTTP client for localhost requests without SSL verification.

    This client is specifically for localhost HTTP (not HTTPS) requests where
    SSL verification would fail. Should only be used for internal coordination.

    Args:
        follow_redirects: Whether to automatically follow redirects (default: True)

    Returns:
        httpx.AsyncClient configured for localhost HTTP requests
    """
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        limits=DEFAULT_LIMITS,
        headers=DEFAULT_HEADERS,
        verify=False,  # noqa: S501 - Intentionally disabled for localhost HTTP; snyk:ignore:python/SSLVerificationBypass
        trust_env=False,  # Don't trust environment proxy settings
        follow_redirects=follow_redirects,  # Configurable redirect handling
        http2=False,  # Disable HTTP/2 for localhost to avoid negotiation issues with uvicorn
    )


def secure_get(url: str, **kwargs: Any) -> httpx.Response:
    """Make a secure GET request with hardened defaults.

    Args:
        url: URL to request
        **kwargs: Additional httpx parameters

    Returns:
        httpx.Response object
    """
    # Ensure security defaults
    kwargs.setdefault("verify", True)
    kwargs.setdefault("timeout", 10.0)
    kwargs.setdefault("follow_redirects", True)  # Enable redirects for OAuth compatibility

    # Merge headers securely
    headers = DEFAULT_HEADERS.copy()
    if "headers" in kwargs:
        headers.update(kwargs["headers"])
    kwargs["headers"] = headers

    return httpx.get(url, **kwargs)


def secure_post(url: str, **kwargs: Any) -> httpx.Response:
    """Make a secure POST request with hardened defaults.

    Args:
        url: URL to request
        **kwargs: Additional httpx parameters

    Returns:
        httpx.Response object
    """
    # Ensure security defaults
    kwargs.setdefault("verify", True)
    kwargs.setdefault("timeout", 10.0)
    kwargs.setdefault("follow_redirects", True)  # Enable redirects for OAuth compatibility

    # Merge headers securely
    headers = DEFAULT_HEADERS.copy()
    if "headers" in kwargs:
        headers.update(kwargs["headers"])
    kwargs["headers"] = headers

    return httpx.post(url, **kwargs)
