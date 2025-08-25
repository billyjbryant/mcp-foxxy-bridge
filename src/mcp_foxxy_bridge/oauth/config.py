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
