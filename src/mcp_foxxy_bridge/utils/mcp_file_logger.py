#
# MCP Foxxy Bridge - MCP Server File Logging
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
"""MCP Server File Logging System.

This module provides dedicated rotating file logging for individual MCP servers,
making it easier to debug issues with specific servers while keeping disk usage
under control through automatic log rotation.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .bridge_home import get_bridge_home


class MCPFileLoggerManager:
    """Manages individual rotating file loggers for MCP servers.

    Each MCP server gets its own log file with automatic rotation based on size.
    This helps with debugging individual server issues while keeping the main
    bridge logs clean.
    """

    def __init__(
        self,
        log_dir: str | None = None,
        max_file_size: int = 1024 * 1024,  # 1MB default
        backup_count: int = 3,
    ) -> None:
        """Initialize the MCP file logger manager.

        Args:
            log_dir: Directory to store MCP server log files (defaults to ~/.foxxy-bridge/logs/mcp-servers)
            max_file_size: Maximum size per log file in bytes (default: 1MB)
            backup_count: Number of backup files to keep (default: 3)
        """
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            bridge_home = get_bridge_home()
            self.log_dir = bridge_home.server_logs_dir

        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self._loggers: dict[str, logging.Logger] = {}
        self._handlers: dict[str, RotatingFileHandler] = {}

        # Create logs directory if it doesn't exist
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_server_logger(self, server_name: str, log_level: str = "INFO") -> logging.Logger:
        """Get or create a rotating file logger for a specific MCP server.

        Args:
            server_name: Name of the MCP server
            log_level: Log level for this server (DEBUG, INFO, WARNING, ERROR)

        Returns:
            Logger instance for the server
        """
        if server_name in self._loggers:
            return self._loggers[server_name]

        # Create logger for this server
        logger_name = f"mcp.server.{server_name}.file"
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Prevent propagation to avoid duplicate logs in main logger
        logger.propagate = False

        # Create rotating file handler
        log_file = self.log_dir / f"{server_name}.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding="utf-8",
        )

        # Create formatter with timestamp and level
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)

        # Store references
        self._loggers[server_name] = logger
        self._handlers[server_name] = handler

        return logger

    def log_server_message(
        self,
        server_name: str,
        message: str,
        level: int = logging.INFO,
        log_level: str = "INFO",
    ) -> None:
        """Log a message to a server's file logger.

        Args:
            server_name: Name of the MCP server
            message: Message to log
            level: Logging level (logging.DEBUG, INFO, WARNING, ERROR)
            log_level: Server's configured log level
        """
        logger = self.get_server_logger(server_name, log_level)
        logger.log(level, "%s", message)

    def close_server_logger(self, server_name: str) -> None:
        """Close and clean up logger for a specific server.

        Args:
            server_name: Name of the MCP server
        """
        if server_name in self._handlers:
            handler = self._handlers.pop(server_name)
            handler.close()

        if server_name in self._loggers:
            logger = self._loggers.pop(server_name)
            for log_handler in logger.handlers[:]:
                log_handler.close()
                logger.removeHandler(log_handler)

    def close_all_loggers(self) -> None:
        """Close and clean up all server loggers."""
        for server_name in list(self._loggers.keys()):
            self.close_server_logger(server_name)

    def get_log_file_path(self, server_name: str) -> Path:
        """Get the log file path for a server.

        Args:
            server_name: Name of the MCP server

        Returns:
            Path to the server's log file
        """
        return self.log_dir / f"{server_name}.log"

    def get_log_files_info(self) -> dict[str, dict[str, Any]]:
        """Get information about all log files.

        Returns:
            Dictionary with server names and their log file info
        """
        info: dict[str, dict[str, Any]] = {}

        for server_name in self._loggers:
            log_file = self.get_log_file_path(server_name)
            if log_file.exists():
                stat = log_file.stat()
                info[server_name] = {
                    "path": str(log_file),
                    "size_bytes": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": stat.st_mtime,
                    "backup_files": [],
                }

                # Check for backup files
                for i in range(1, self.backup_count + 1):
                    backup_file = Path(f"{log_file}.{i}")
                    if backup_file.exists():
                        backup_stat = backup_file.stat()
                        info[server_name]["backup_files"].append(
                            {
                                "path": str(backup_file),
                                "size_bytes": backup_stat.st_size,
                                "size_mb": round(backup_stat.st_size / (1024 * 1024), 2),
                                "modified": backup_stat.st_mtime,
                            }
                        )

        return info


# Global instance for easy access
_mcp_file_logger_manager: MCPFileLoggerManager | None = None


def get_mcp_file_logger_manager(
    log_dir: str | None = None,
    max_file_size: int = 1024 * 1024,  # 1MB
    backup_count: int = 3,
) -> MCPFileLoggerManager:
    """Get the global MCP file logger manager instance.

    Args:
        log_dir: Directory to store MCP server log files (defaults to ~/.foxxy-bridge/logs/mcp-servers)
        max_file_size: Maximum size per log file in bytes
        backup_count: Number of backup files to keep

    Returns:
        Global MCPFileLoggerManager instance
    """
    global _mcp_file_logger_manager

    if _mcp_file_logger_manager is None:
        _mcp_file_logger_manager = MCPFileLoggerManager(
            log_dir=log_dir, max_file_size=max_file_size, backup_count=backup_count
        )

    return _mcp_file_logger_manager


def log_to_server_file(server_name: str, message: str, level: int = logging.INFO, log_level: str = "INFO") -> None:
    """Convenience function to log a message to a server's file.

    Args:
        server_name: Name of the MCP server
        message: Message to log
        level: Logging level
        log_level: Server's configured log level
    """
    manager = get_mcp_file_logger_manager()
    manager.log_server_message(server_name, message, level, log_level)


def cleanup_mcp_file_loggers() -> None:
    """Clean up all MCP file loggers."""
    global _mcp_file_logger_manager

    if _mcp_file_logger_manager is not None:
        _mcp_file_logger_manager.close_all_loggers()
        _mcp_file_logger_manager = None
