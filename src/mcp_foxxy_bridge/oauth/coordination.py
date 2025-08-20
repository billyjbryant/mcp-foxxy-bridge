"""Authentication coordination for managing OAuth flow across multiple processes."""

import contextlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from .events import EventEmitter
from .utils import FileLock, get_lockfile_path, is_pid_running

logger = logging.getLogger(__name__)


# OAuth callback handling is now integrated with the bridge server
# No need for separate callback server classes


class LockfileData:
    """Structure for lockfile data."""

    def __init__(self, pid: int, port: int, endpoint: str) -> None:
        self.pid = pid
        self.port = port
        self.endpoint = endpoint

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LockfileData":
        """Create LockfileData from dictionary."""
        return cls(pid=data["pid"], port=data["port"], endpoint=data["endpoint"])

    def to_dict(self) -> dict[str, Any]:
        """Convert LockfileData to dictionary."""
        return {"pid": self.pid, "port": self.port, "endpoint": self.endpoint}


def read_lockfile(lockfile_path: Path) -> LockfileData | None:
    """Read and parse lockfile data."""
    try:
        with lockfile_path.open() as f:
            data = json.load(f)
            return LockfileData.from_dict(data)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def write_lockfile(lockfile_path: Path, data: LockfileData) -> None:
    """Write lockfile data."""
    with lockfile_path.open("w") as f:
        json.dump(data.to_dict(), f)


def is_lock_valid(lockfile_data: LockfileData) -> bool:
    """Check if lockfile represents a valid running process."""
    return is_pid_running(lockfile_data.pid)


def wait_for_authentication(port: int, timeout: float = 300.0) -> bool:
    """Wait for authentication to complete on another process."""
    start_time = time.time()
    check_url = f"http://localhost:{port}/status"

    while time.time() - start_time < timeout:
        try:
            response = requests.get(check_url, timeout=1.0)  # type: ignore[attr-defined, no-untyped-call]
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "completed":
                    return True
                if data.get("status") == "error":
                    return False
        except (requests.RequestException, json.JSONDecodeError):  # type: ignore[attr-defined]
            pass

        time.sleep(1.0)

    return False


def coordinate_auth(server_url_hash: str, callback_port: int, events: EventEmitter) -> tuple[bool, None]:
    """Coordinate authentication across multiple processes.

    Returns:
        (should_start_new_auth, None)
        - should_start_new_auth: True if this process should handle auth
        - None: No callback server needed (bridge server handles OAuth callbacks)
    """
    lockfile_path = get_lockfile_path(server_url_hash)

    # Skip lockfile coordination on Windows due to file locking issues
    if os.name == "nt":
        return True, None

    # Check for existing lockfile
    existing_lock = read_lockfile(lockfile_path)

    if existing_lock and is_lock_valid(existing_lock):
        logger.info(f"Found existing authentication process (PID: {existing_lock.pid})")
        logger.info("Waiting for authentication to complete...")

        success = wait_for_authentication(existing_lock.port)
        if success:
            logger.info("Authentication completed by existing process")
            return False, None
        logger.info("Authentication failed or timed out, starting new process")

    # Try to acquire lock and start new authentication
    try:
        with FileLock(lockfile_path):
            # Create lockfile data
            lock_data = LockfileData(pid=os.getpid(), port=callback_port, endpoint=f"http://localhost:{callback_port}")
            write_lockfile(lockfile_path, lock_data)

            return True, None

    except RuntimeError:
        # Could not acquire lock, another process is starting auth
        logger.info("Another process is starting authentication, waiting...")
        time.sleep(2)  # Give the other process time to set up

        # Try to wait for the other process
        retrieved_lock_data: LockfileData | None = read_lockfile(lockfile_path)
        if retrieved_lock_data and is_lock_valid(retrieved_lock_data):
            success = wait_for_authentication(retrieved_lock_data.port)
            if success:
                return False, None

        # Fallback to starting our own auth
        return True, None


def create_lazy_auth_coordinator(server_url_hash: str, callback_port: int, events: EventEmitter) -> Any:
    """Create a lazy authentication coordinator."""

    def coordinate() -> Any:
        return coordinate_auth(server_url_hash, callback_port, events)

    return coordinate


def cleanup_lockfile(server_url_hash: str) -> None:
    """Clean up lockfile for the given server."""
    lockfile_path = get_lockfile_path(server_url_hash)
    with contextlib.suppress(FileNotFoundError):
        lockfile_path.unlink()
