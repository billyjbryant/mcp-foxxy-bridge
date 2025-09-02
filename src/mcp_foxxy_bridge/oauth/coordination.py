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

"""Authentication coordination for managing OAuth flow across multiple processes."""

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from mcp_foxxy_bridge.utils.logging import get_logger

from .config import OAUTH_USER_AGENT
from .events import EventEmitter
from .utils import FileLock, get_lockfile_path, is_pid_running

logger = get_logger(__name__, facility="OAUTH")


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
            # Disable SSL verification for localhost HTTP URLs
            is_localhost = check_url.startswith(("http://localhost", "http://127.0.0.1"))
            response = httpx.get(
                check_url,
                timeout=1.0,
                verify=not is_localhost,  # Only disable SSL verification for localhost HTTP
                headers={"User-Agent": OAUTH_USER_AGENT},
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "completed":
                    return True
                if data.get("status") == "error":
                    return False
        except (httpx.HTTPError, json.JSONDecodeError):
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
