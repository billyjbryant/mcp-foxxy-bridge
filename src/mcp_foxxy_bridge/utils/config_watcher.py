#
# MCP Foxxy Bridge - Configuration File Watcher
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
"""Configuration file watcher for dynamic config reloading."""

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from mcp_foxxy_bridge.utils.logging import get_logger

logger = get_logger(__name__, facility="UTILS")


class ConfigFileHandler(FileSystemEventHandler):
    """File system event handler for configuration file changes."""

    def __init__(
        self,
        config_path: str,
        reload_callback: Callable[[], Awaitable[bool]],
        debounce_ms: int = 1000,
        *,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Initialize the config file handler.

        Args:
            config_path: Path to the configuration file to watch
            reload_callback: Async callback to call when config changes
            debounce_ms: Debounce time in milliseconds to avoid rapid reloads
            event_loop: Event loop to schedule tasks in
        """
        super().__init__()
        self.config_path = Path(config_path).resolve()
        self.reload_callback = reload_callback
        self.debounce_ms = debounce_ms
        self.event_loop = event_loop
        self._last_reload_time = 0.0
        self._reload_lock = threading.Lock()

        logger.debug("Watching config file: %s", self.config_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        event_path = Path(str(event.src_path)).resolve()

        # Check if the modified file is our config file
        if event_path == self.config_path:
            logger.debug("Config file modified: %s", event_path)
            self._schedule_reload()

    def _schedule_reload(self) -> None:
        """Schedule a debounced config reload."""
        current_time = time.time()

        with self._reload_lock:
            # Update the last reload time to implement debouncing
            self._last_reload_time = current_time

        # Schedule the actual reload after debounce period
        try:
            asyncio.run_coroutine_threadsafe(self._debounced_reload(current_time), self.event_loop)
        except RuntimeError:
            logger.warning("Could not schedule config reload - no event loop available")

    async def _debounced_reload(self, scheduled_time: float) -> None:
        """Perform debounced config reload."""
        try:
            # Wait for debounce period
            await asyncio.sleep(self.debounce_ms / 1000.0)

            # Check if this is still the latest reload request
            with self._reload_lock:
                if scheduled_time < self._last_reload_time:
                    # A newer reload was scheduled, skip this one
                    logger.debug("Config reload skipped (newer reload scheduled)")
                    return

            logger.info("Configuration file changed, reloading...")
            success = await self.reload_callback()

            if success:
                logger.info("Configuration reloaded successfully")
            else:
                logger.error("Failed to reload configuration")

        except asyncio.CancelledError:
            logger.debug("Config reload cancelled")
        except Exception:
            logger.exception("Error during config reload")


class ConfigWatcher:
    """Configuration file watcher that monitors for changes."""

    def __init__(
        self,
        config_path: str,
        reload_callback: Callable[[], Awaitable[bool]],
        debounce_ms: int = 1000,
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the config watcher.

        Args:
            config_path: Path to the configuration file to watch
            reload_callback: Async callback to call when config changes
            debounce_ms: Debounce time in milliseconds to avoid rapid reloads
            enabled: Whether the watcher is enabled
        """
        self.config_path = Path(config_path).resolve()
        self.reload_callback = reload_callback
        self.debounce_ms = debounce_ms
        self.enabled = enabled

        self._observer: Any = None
        self._handler: ConfigFileHandler | None = None

    async def start(self) -> None:
        """Start watching the configuration file."""
        if not self.enabled:
            logger.info("Configuration file watching is disabled")
            return

        if not self.config_path.exists():
            logger.warning("Configuration file does not exist: %s", self.config_path)
            return

        try:
            # Create handler and observer
            self._handler = ConfigFileHandler(
                str(self.config_path),
                self.reload_callback,
                self.debounce_ms,
                event_loop=asyncio.get_running_loop(),
            )

            self._observer = Observer()

            # Watch the directory containing the config file
            watch_dir = self.config_path.parent
            self._observer.schedule(
                self._handler,
                str(watch_dir),
                recursive=False,
            )

            # Start the observer
            self._observer.start()
            logger.debug("Started watching config file: %s", self.config_path)

        except Exception:
            logger.exception("Failed to start config file watcher")
            await self.stop()

    async def stop(self) -> None:
        """Stop watching the configuration file."""
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5.0)
                logger.info("Stopped config file watcher")
            except Exception:
                logger.exception("Error stopping config file watcher")
            finally:
                self._observer = None
                self._handler = None

    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._observer is not None and self._observer.is_alive()

    async def __aenter__(self) -> "ConfigWatcher":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Async context manager exit."""
        await self.stop()
