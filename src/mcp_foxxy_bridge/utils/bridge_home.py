#
# MCP Foxxy Bridge - Bridge Home Directory Management
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
"""Bridge Home Directory Management.

This module manages the bridge's home directory structure (~/.config/foxxy-bridge)
which includes:
- Configuration files
- Log files for individual MCP servers
- OAuth tokens and authentication data
- Cache files
- Bridge state and metadata
"""

import contextlib
import os
import time
from pathlib import Path
from typing import Any

from .config_migration import get_config_dir


class BridgeHome:
    """Manages the bridge's home directory structure.

    Provides standardized paths for configuration, logs, and other bridge data
    with automatic directory creation as needed.
    """

    def __init__(self, home_dir: str | None = None) -> None:
        """Initialize bridge home directory manager.

        Args:
            home_dir: Custom home directory path (defaults to ~/.config/foxxy-bridge)
        """
        if home_dir:
            self.home_dir = Path(home_dir).expanduser()
        else:
            # Use centralized config directory utility
            self.home_dir = get_config_dir()

        # Define standard subdirectories
        self.config_dir = self.home_dir / "config"
        self.logs_dir = self.home_dir / "logs"
        self.server_logs_dir = self.logs_dir / "mcp-servers"
        self.auth_dir = self.home_dir / "auth"
        self.cache_dir = self.home_dir / "cache"
        self.state_dir = self.home_dir / "state"

        # Ensure all directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create all necessary directories if they don't exist."""
        directories = [
            self.home_dir,
            self.config_dir,
            self.logs_dir,
            self.server_logs_dir,
            self.auth_dir,
            self.cache_dir,
            self.state_dir,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def get_config_path(self, filename: str = "config.json") -> Path:
        """Get path to a configuration file.

        Args:
            filename: Name of the config file

        Returns:
            Path to the config file in the config directory
        """
        return self.config_dir / filename

    def get_default_config_paths(self) -> list[Path]:
        """Get list of default config file paths to search.

        Returns ordered list of paths to check for config files.

        Returns:
            List of paths in priority order
        """
        return [
            self.get_config_path("config.json"),
            self.get_config_path("mcp-foxxy-config.json"),
            self.get_config_path("bridge-config.json"),
            Path("config.json"),  # Current directory fallback
            Path("mcp-foxxy-config.json"),  # Current directory fallback
        ]

    def get_server_log_path(self, server_name: str) -> Path:
        """Get path to a server's log file.

        Args:
            server_name: Name of the MCP server

        Returns:
            Path to the server's log file
        """
        return self.server_logs_dir / f"{server_name}.log"

    def get_bridge_log_path(self) -> Path:
        """Get path to the main bridge log file.

        Returns:
            Path to the main bridge log file
        """
        return self.logs_dir / "bridge.log"

    def get_auth_token_path(self, server_name: str) -> Path:
        """Get path to a server's auth token file.

        Args:
            server_name: Name of the MCP server

        Returns:
            Path to the server's auth token file
        """
        return self.auth_dir / f"{server_name}-tokens.json"

    def get_cache_path(self, cache_name: str) -> Path:
        """Get path to a cache file.

        Args:
            cache_name: Name of the cache file

        Returns:
            Path to the cache file
        """
        return self.cache_dir / cache_name

    def get_state_path(self, state_name: str) -> Path:
        """Get path to a state file.

        Args:
            state_name: Name of the state file

        Returns:
            Path to the state file
        """
        return self.state_dir / state_name

    def cleanup_old_logs(self, max_age_days: int = 30) -> None:
        """Clean up old log files.

        Args:
            max_age_days: Maximum age of log files to keep
        """
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        # Clean up server logs
        for log_file in self.server_logs_dir.glob("*.log*"):
            if log_file.stat().st_mtime < cutoff_time:
                with contextlib.suppress(OSError):
                    log_file.unlink()

    def get_info(self) -> dict[str, Any]:
        """Get information about the bridge home directory.

        Returns:
            Dictionary with home directory information
        """

        def get_dir_size(path: Path) -> int:
            """Get total size of directory in bytes."""
            total = 0
            try:
                for entry in path.rglob("*"):
                    if entry.is_file():
                        total += entry.stat().st_size
            except OSError:
                pass
            return total

        info = {
            "home_directory": str(self.home_dir),
            "exists": self.home_dir.exists(),
            "directories": {
                "config": {
                    "path": str(self.config_dir),
                    "exists": self.config_dir.exists(),
                    "size_bytes": get_dir_size(self.config_dir) if self.config_dir.exists() else 0,
                },
                "logs": {
                    "path": str(self.logs_dir),
                    "exists": self.logs_dir.exists(),
                    "size_bytes": get_dir_size(self.logs_dir) if self.logs_dir.exists() else 0,
                },
                "server_logs": {
                    "path": str(self.server_logs_dir),
                    "exists": self.server_logs_dir.exists(),
                    "size_bytes": get_dir_size(self.server_logs_dir) if self.server_logs_dir.exists() else 0,
                    "file_count": len(list(self.server_logs_dir.glob("*"))) if self.server_logs_dir.exists() else 0,
                },
                "auth": {
                    "path": str(self.auth_dir),
                    "exists": self.auth_dir.exists(),
                    "size_bytes": get_dir_size(self.auth_dir) if self.auth_dir.exists() else 0,
                },
                "cache": {
                    "path": str(self.cache_dir),
                    "exists": self.cache_dir.exists(),
                    "size_bytes": get_dir_size(self.cache_dir) if self.cache_dir.exists() else 0,
                },
                "state": {
                    "path": str(self.state_dir),
                    "exists": self.state_dir.exists(),
                    "size_bytes": get_dir_size(self.state_dir) if self.state_dir.exists() else 0,
                },
            },
        }

        # Add total size
        directories_data = info["directories"]
        if isinstance(directories_data, dict):
            total_bytes = sum(dir_info["size_bytes"] for dir_info in directories_data.values())
            info["total_size_bytes"] = total_bytes
            info["total_size_mb"] = round(total_bytes / (1024 * 1024), 2)
        else:
            info["total_size_bytes"] = 0
            info["total_size_mb"] = 0.0

        return info


# Global instance
_bridge_home: BridgeHome | None = None


def get_bridge_home(home_dir: str | None = None) -> BridgeHome:
    """Get the global bridge home directory manager.

    Args:
        home_dir: Custom home directory path

    Returns:
        BridgeHome instance
    """
    global _bridge_home

    if _bridge_home is None:
        _bridge_home = BridgeHome(home_dir)

    return _bridge_home


def find_config_file(config_path: str | None = None) -> Path | None:
    """Find a configuration file using standard search paths.

    Args:
        config_path: Explicit config path, if provided

    Returns:
        Path to found config file, or None if not found
    """
    bridge_home = get_bridge_home()

    # If explicit path provided, use it
    if config_path:
        path = Path(config_path).expanduser()
        if path.exists():
            return path
        return None

    # Check environment variable
    env_config = os.environ.get("MCP_BRIDGE_CONFIG")
    if env_config:
        path = Path(env_config).expanduser()
        if path.exists():
            return path

    # Check default paths
    for path in bridge_home.get_default_config_paths():
        if path.exists():
            return path

    return None
