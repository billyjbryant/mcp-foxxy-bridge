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

"""Simple event emitter implementation for Python."""

import threading
from collections.abc import Callable
from typing import Any

from mcp_foxxy_bridge.utils.logging import get_logger

logger = get_logger(__name__, facility="OAUTH")


class EventEmitter:
    """Simple event emitter similar to Node.js EventEmitter."""

    def __init__(self) -> None:
        self._events: dict[str, list[Callable[..., Any]]] = {}
        self._lock = threading.Lock()

    def on(self, event: str, listener: Callable[..., Any]) -> "EventEmitter":
        """Add a listener for the specified event."""
        with self._lock:
            if event not in self._events:
                self._events[event] = []
            self._events[event].append(listener)
        return self

    def once(self, event: str, listener: Callable[..., Any]) -> "EventEmitter":
        """Add a one-time listener for the specified event."""

        def wrapper(*args: Any, **kwargs: Any) -> None:
            self.off(event, wrapper)
            listener(*args, **kwargs)

        wrapper._original_listener = listener  # type: ignore[attr-defined]  # noqa: SLF001
        return self.on(event, wrapper)

    def off(self, event: str, listener: Callable[..., Any]) -> "EventEmitter":
        """Remove a listener for the specified event."""
        with self._lock:
            if event in self._events:
                # Handle wrapped listeners from once()
                listeners_to_remove = [
                    listener_item
                    for listener_item in self._events[event]
                    if listener_item == listener or getattr(listener_item, "_original_listener", None) == listener
                ]

                for listener_item in listeners_to_remove:
                    self._events[event].remove(listener_item)

                if not self._events[event]:
                    del self._events[event]
        return self

    def emit(self, event: str, *args: Any, **kwargs: Any) -> bool:
        """Emit an event with the given arguments."""
        with self._lock:
            if event not in self._events:
                return False

            listeners = self._events[event].copy()

        # Call listeners outside of lock to avoid deadlock
        for listener in listeners:
            try:
                listener(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error in event listener for '{event}': {e}")

        return len(listeners) > 0

    def remove_all_listeners(self, event: str | None = None) -> "EventEmitter":
        """Remove all listeners for a specific event or all events."""
        with self._lock:
            if event is None:
                self._events.clear()
            elif event in self._events:
                del self._events[event]
        return self

    def listeners(self, event: str) -> list[Callable[..., Any]]:
        """Get all listeners for the specified event."""
        with self._lock:
            return self._events.get(event, []).copy()

    def listener_count(self, event: str) -> int:
        """Get the number of listeners for the specified event."""
        with self._lock:
            return len(self._events.get(event, []))
