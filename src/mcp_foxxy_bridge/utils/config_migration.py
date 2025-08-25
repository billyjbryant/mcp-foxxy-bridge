"""Configuration directory migration utility.

This module handles migrating from legacy configuration directory structure
to XDG Base Directory Specification compliant paths.

Legacy: ~/.foxxy-bridge/
New:    ~/.config/foxxy-bridge/
"""

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def get_config_directories() -> tuple[Path, Path]:
    """Get legacy and new configuration directory paths.

    Returns:
        Tuple of (legacy_dir, new_dir) paths
    """
    home = Path.home()
    legacy_dir = home / ".foxxy-bridge"

    # Check for custom OAuth config directory (for tests)
    oauth_config_dir = os.environ.get("MCP_OAUTH_CONFIG_DIR")
    if oauth_config_dir:
        custom_dir = Path(oauth_config_dir)
        # Validate path to prevent traversal
        custom_str = str(custom_dir)
        if ".." in custom_str and ("/../" in custom_str or custom_str.endswith("/..")):
            raise ValueError(f"Path traversal attempt detected: {custom_dir}")
        new_dir = custom_dir
    else:
        # Use XDG Base Directory Specification
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        new_dir = Path(xdg_config_home) / "foxxy-bridge" if xdg_config_home else home / ".config" / "foxxy-bridge"

    return legacy_dir, new_dir


def needs_migration() -> bool:
    """Check if configuration migration is needed.

    Returns:
        True if migration is needed, False otherwise
    """
    legacy_dir, new_dir = get_config_directories()

    # Migration needed if legacy directory exists and new directory doesn't
    return legacy_dir.exists() and not new_dir.exists()


def migrate_config_directory() -> bool:
    """Migrate configuration directory from legacy to XDG location.

    Returns:
        True if migration was successful or not needed, False if failed
    """
    if not needs_migration():
        return True

    legacy_dir, new_dir = get_config_directories()

    try:
        logger.info("Migrating configuration directory from %s to %s", legacy_dir, new_dir)

        # Ensure parent directory exists
        new_dir.parent.mkdir(parents=True, exist_ok=True)

        # Move the entire directory
        shutil.move(str(legacy_dir), str(new_dir))

        logger.info("Configuration directory migration completed successfully")
        return True

    except Exception:
        logger.exception("Configuration directory migration failed")
        logger.info("You may need to manually move %s to %s", legacy_dir, new_dir)
        return False


def ensure_config_directory() -> Path:
    """Ensure configuration directory exists and migrate if needed.

    Returns:
        Path to the configuration directory
    """
    # Attempt migration first
    migrate_config_directory()

    # Get the new directory path
    _, new_dir = get_config_directories()

    # Ensure it exists
    new_dir.mkdir(parents=True, exist_ok=True)

    return new_dir


def get_config_dir() -> Path:
    """Get the main configuration directory for the application.

    This is the primary function that all modules should use to get
    the configuration directory. It handles migration automatically.

    Returns:
        Path to the configuration directory (~/.config/foxxy-bridge/)
    """
    return ensure_config_directory()


def get_auth_dir() -> Path:
    """Get the OAuth authentication directory.

    Returns:
        Path to the auth directory (~/.config/foxxy-bridge/auth/)
    """
    return get_config_dir() / "auth"


def get_logs_dir() -> Path:
    """Get the logs directory.

    Returns:
        Path to the logs directory (~/.config/foxxy-bridge/logs/)
    """
    return get_config_dir() / "logs"


def get_server_logs_dir() -> Path:
    """Get the MCP server logs directory.

    Returns:
        Path to the server logs directory (~/.config/foxxy-bridge/logs/mcp-servers/)
    """
    return get_logs_dir() / "mcp-servers"
