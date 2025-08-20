#
# MCP Foxxy Bridge - Child Process Logging
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
"""Child Process Logging Utilities.

This module provides utilities for capturing and redirecting child process
output through the bridge's unified Rich logging system, ensuring consistent
formatting and log level control across all MCP servers.
"""

import asyncio
import contextlib
import logging
import re

from .mcp_file_logger import log_to_server_file

logger = logging.getLogger(__name__)


class ProcessLogHandler:
    """Handles logging output from child MCP server processes.

    Captures stdout/stderr from child processes and redirects them through
    the bridge's unified logging system with proper formatting and level control.
    """

    def __init__(self, server_name: str, log_level: str = "ERROR") -> None:
        """Initialize the process log handler.

        Args:
            server_name: Name of the server for log context
            log_level: Minimum log level to capture (DEBUG, INFO, WARNING, ERROR)
        """
        self.server_name = server_name
        self.log_level = getattr(logging, log_level.upper(), logging.ERROR)
        self.log_level_name = log_level.upper()
        self.server_logger = logging.getLogger(f"mcp.server.{server_name}")

        # Patterns to detect log levels in child process output
        self.log_patterns = [
            (
                re.compile(r"(?i)\b(error|err|exception|traceback|failed|failure)\b"),
                logging.ERROR,
            ),
            (re.compile(r"(?i)\b(warning|warn|alert)\b"), logging.WARNING),
            (
                re.compile(r"(?i)\b(info|information|started|ready|success)\b"),
                logging.INFO,
            ),
            (re.compile(r"(?i)\b(debug|trace|verbose)\b"), logging.DEBUG),
        ]

    def should_log(self, level: int) -> bool:
        """Check if a log level should be captured based on configuration."""
        return level >= self.log_level

    def parse_log_level(self, message: str) -> int:
        """Parse log level from message content.

        Args:
            message: Log message to analyze

        Returns:
            Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        message_lower = message.lower()

        # Check for explicit log level indicators
        for pattern, level in self.log_patterns:
            if pattern.search(message):
                return level

        # Check for common error indicators
        if any(
            indicator in message_lower
            for indicator in [
                "traceback",
                "exception",
                "error:",
                "failed",
                "cannot",
                "unable",
                "invalid",
            ]
        ):
            return logging.ERROR

        # Check for warnings
        if any(indicator in message_lower for indicator in ["warning:", "warn:", "deprecated", "caution"]):
            return logging.WARNING

        # Check for info messages
        if any(
            indicator in message_lower
            for indicator in [
                "starting",
                "started",
                "ready",
                "listening",
                "serving",
                "connected",
            ]
        ):
            return logging.INFO

        # Default to DEBUG for unclassified messages
        return logging.DEBUG

    def clean_message(self, message: str) -> str:
        """Clean and format log message from child process.

        Args:
            message: Raw log message

        Returns:
            Cleaned message suitable for logging
        """
        # Remove common timestamp prefixes and log level prefixes
        cleaned = re.sub(r"^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}[^\s]*\s*", "", message)
        cleaned = re.sub(r"^\[\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\]\s*", "", cleaned)
        cleaned = re.sub(
            r"^(DEBUG|INFO|WARNING|ERROR|WARN|ERR):\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^(debug|info|warning|error):\s*", "", cleaned, flags=re.IGNORECASE)

        # Remove common noise from package managers and development tools
        noise_patterns = [
            # Package manager noise
            "resolving dependencies",
            "preparing packages",
            "installing wheels",
            "installed",
            "packages in",
            "ms",
            "downloaded",
            # AWS SDK noise
            "found credentials",
            "using profile",
            "region",
            "boto3",
            "aws-cli",
            "credential_source",
            "credentials found",
            # HTTP/networking noise
            "connection pool",
            "starting new https connection",
            "resetting dropped connection",
            "http connection",
            "ssl context",
            "certificate verification",
            # Development/build noise
            "webpack",
            "esbuild",
            "rollup",
            "typescript",
            "tsc",
            "node_modules",
            "package.json",
            "npm",
            "yarn",
            "pnpm",
            # Generic progress indicators
            "loading...",
            "processing...",
            "waiting...",
            "...",
        ]

        cleaned_lower = cleaned.lower()
        if any(noise in cleaned_lower for noise in noise_patterns):
            return ""

        # Remove lines that are just progress indicators or dots
        if re.match(r"^[.\-_=\s]*$", cleaned) or len(cleaned.strip()) < 3:
            return ""

        # Remove empty lines and whitespace-only messages
        cleaned = cleaned.strip()
        if not cleaned or cleaned.isspace():
            return ""

        return cleaned

    def log_message(self, message: str, is_stderr: bool = False) -> None:
        """Log a message from child process through unified logging system.

        Args:
            message: Message to log
            is_stderr: Whether message came from stderr
        """
        cleaned = self.clean_message(message)
        if not cleaned:
            return

        # Parse log level from message content
        detected_level = self.parse_log_level(cleaned)

        # Upgrade stderr messages to at least WARNING level
        if is_stderr and detected_level < logging.WARNING:
            detected_level = logging.WARNING

        # Check if we should log this level
        if not self.should_log(detected_level):
            return

        # Log through the server-specific logger (for console output)
        self.server_logger.log(detected_level, "%s", cleaned)

        # Also log to the server's dedicated file (always log to file regardless of console level)
        log_to_server_file(self.server_name, cleaned, detected_level, self.log_level_name)


async def capture_process_output(
    process: asyncio.subprocess.Process, server_name: str, log_level: str = "ERROR"
) -> None:
    """Capture and redirect process output through unified logging.

    Args:
        process: The subprocess to capture output from
        server_name: Name of the server for logging context
        log_level: Minimum log level to capture
    """
    handler = ProcessLogHandler(server_name, log_level)

    async def read_stream(stream: asyncio.StreamReader, is_stderr: bool = False) -> None:
        """Read from a stream and log messages."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break

                try:
                    message = line.decode("utf-8", errors="replace").rstrip("\n\r")
                    handler.log_message(message, is_stderr)
                except (UnicodeDecodeError, AttributeError) as e:
                    logger.debug("Log line processing error: %s", type(e).__name__)
                except Exception as e:
                    logger.warning("Unexpected log processing error: %s", type(e).__name__)

        except (OSError, asyncio.CancelledError) as e:
            logger.debug("Stream read error from %s: %s", "stderr" if is_stderr else "stdout", type(e).__name__)
        except Exception as e:
            logger.warning(
                "Unexpected stream error from %s: %s",
                "stderr" if is_stderr else "stdout",
                type(e).__name__,
            )

    # Start tasks to read both stdout and stderr
    stdout_task = None
    stderr_task = None

    try:
        if process.stdout:
            stdout_task = asyncio.create_task(read_stream(process.stdout, is_stderr=False))
        if process.stderr:
            stderr_task = asyncio.create_task(read_stream(process.stderr, is_stderr=True))

        # Wait for both tasks to complete
        tasks = [task for task in [stdout_task, stderr_task] if task]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    except (OSError, asyncio.CancelledError) as e:
        logger.debug("Process output capture error: %s", type(e).__name__)
    except Exception as e:
        logger.warning("Unexpected process capture error: %s", type(e).__name__)
    finally:
        # Cancel any remaining tasks
        for task in [stdout_task, stderr_task]:
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
