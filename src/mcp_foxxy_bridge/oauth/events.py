"""Simple event emitter implementation for Python."""

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


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
