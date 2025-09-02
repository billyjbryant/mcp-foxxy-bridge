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

"""Centralized OAuth client configuration constants."""

from importlib.metadata import version
from pathlib import Path


def get_package_version() -> str:
    """Get the package version using the same logic as __main__.py."""
    try:
        return version("mcp-foxxy-bridge")
    except Exception:
        try:
            # Try to read from VERSION file
            version_file = Path(__file__).parent.parent.parent.parent / "VERSION"
            return version_file.read_text().strip() if version_file.exists() else "unknown"
        except Exception:
            return "unknown"


# OAuth Client Configuration Constants
OAUTH_CLIENT_NAME = "MCP Foxxy Bridge"
OAUTH_CLIENT_URI = "https://github.com/billyjbryant/mcp-foxxy-bridge"
OAUTH_SOFTWARE_ID = "2e6dc280-f3c3-4e01-99a7-8181dbd1d23d"

# Get version with "v" prefix for better identification
OAUTH_SOFTWARE_VERSION = f"v{get_package_version()}"

# User-Agent for HTTP requests
OAUTH_USER_AGENT = f"mcp-foxxy-bridge/{get_package_version()} (MCP Client)"


def get_oauth_client_config() -> dict[str, str]:
    """Get OAuth client configuration as a dictionary.

    Returns:
        Dictionary containing OAuth client configuration constants
    """
    return {
        "client_name": OAUTH_CLIENT_NAME,
        "client_uri": OAUTH_CLIENT_URI,
        "software_id": OAUTH_SOFTWARE_ID,
        "software_version": OAUTH_SOFTWARE_VERSION,
        "user_agent": OAUTH_USER_AGENT,
    }
