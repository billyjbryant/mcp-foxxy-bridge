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

"""Utility functions for MCP OAuth implementation."""

import base64
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp_foxxy_bridge.utils.config_migration import get_auth_dir, get_config_dir
from mcp_foxxy_bridge.utils.logging import get_logger

try:
    import keyring
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False


def get_server_url_hash(server_url: str) -> str:
    """Generate a short hash for the server URL to use in lockfile names.

    Uses SHA-256 for better security practices, even though this is only for file naming.
    We only need a consistent, collision-resistant identifier.

    Args:
        server_url: The server URL to hash

    Returns:
        A 12-character hex string hash of the URL
    """
    return hashlib.sha256(server_url.encode()).hexdigest()[:12]  # Slightly longer for SHA-256


# Security validation functions


def _validate_server_name(server_name: str) -> str:
    """Validate and sanitize server name to prevent path traversal.

    Args:
        server_name: The server name to validate

    Returns:
        Sanitized server name

    Raises:
        ValueError: If server name contains dangerous patterns
    """
    if not server_name or not isinstance(server_name, str):
        raise ValueError("Server name must be a non-empty string")

    # Check for path traversal attempts (critical security check)
    if ".." in server_name or "/" in server_name or "\\" in server_name:
        raise ValueError(f"Server name '{server_name}' contains invalid path characters")

    # Normalize to alphanumeric, underscores, and hyphens only, and lowercase for consistency
    # Convert common special chars: spaces and plus to hyphens, dots to underscores, then remove others
    sanitized = server_name.lower().replace(" ", "-").replace("+", "-").replace(".", "_")
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", sanitized)

    # Clean up consecutive hyphens and underscores for better readability
    sanitized = re.sub(r"-+", "-", sanitized)  # Multiple hyphens → single hyphen
    sanitized = re.sub(r"_+", "_", sanitized)  # Multiple underscores → single underscore

    # Remove leading/trailing hyphens and underscores
    sanitized = sanitized.strip("-_")

    # Ensure the normalized name is not empty after cleaning
    if not sanitized:
        raise ValueError(f"Server name '{server_name}' results in empty name after normalization")

    # Ensure reasonable length
    if len(sanitized) > 64:
        sanitized = sanitized[:64]

    return sanitized


def _validate_config_path(path: Path) -> Path:
    """Validate configuration path to prevent path traversal.

    Args:
        path: The path to validate

    Returns:
        Validated path

    Raises:
        ValueError: If path contains traversal attempts
    """
    # Resolve to absolute path to prevent traversal
    resolved = path.resolve()

    # Check for obvious traversal patterns in the original path string
    path_str = str(path)
    if ".." in path_str and ("/../" in path_str or path_str.endswith("/..")):
        raise ValueError(f"Path traversal attempt detected: {path}")

    # For custom config directories, be more permissive but still safe
    # Use centralized config directory utility

    config_base = get_config_dir()

    # If the path is under home directory, it's generally safe
    home = Path.home()
    try:
        resolved.relative_to(home)
        return resolved  # Path is under home directory, allow it
    except ValueError:
        pass

    # If it's specifically in the foxxy-bridge config structure, allow it
    try:
        resolved.relative_to(config_base)
        return resolved
    except ValueError:
        # Only reject paths that are clearly trying to escape home directory
        if not str(resolved).startswith(str(home)):
            raise ValueError(f"Path traversal attempt detected: {path}") from None
        return resolved


# Encryption functions for secure token storage


def _get_encryption_key(server_name: str) -> bytes:
    """Get or create encryption key for server tokens.

    Args:
        server_name: Name of the server

    Returns:
        Encryption key bytes
    """
    if not ENCRYPTION_AVAILABLE:
        raise RuntimeError("Encryption dependencies not available (cryptography, keyring)")

    # Use keyring to store the master key securely
    keyring_service = "mcp-foxxy-bridge"
    keyring_username = f"encryption-{server_name}"

    # Try to get existing key
    stored_key = keyring.get_password(keyring_service, keyring_username)

    if stored_key:
        return base64.b64decode(stored_key.encode())

    # Generate new key if none exists
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )

    # Create a master password from system entropy and server name
    master_password = f"{server_name}-{os.urandom(32).hex()}".encode()
    key = kdf.derive(master_password)

    # Store the key securely
    encoded_key = base64.b64encode(key).decode()
    keyring.set_password(keyring_service, keyring_username, encoded_key)

    return key


def _encrypt_data(data: str, server_name: str) -> str:
    """Encrypt sensitive data using Fernet encryption.

    Args:
        data: Data to encrypt
        server_name: Server name for key derivation

    Returns:
        Base64 encoded encrypted data
    """
    if not ENCRYPTION_AVAILABLE:
        raise RuntimeError("Encryption dependencies not available")

    key = _get_encryption_key(server_name)
    fernet = Fernet(base64.urlsafe_b64encode(key[:32]))  # Fernet needs 32 bytes

    encrypted = fernet.encrypt(data.encode())
    return base64.b64encode(encrypted).decode()


def _decrypt_data(encrypted_data: str, server_name: str) -> str:
    """Decrypt sensitive data using Fernet decryption.

    Args:
        encrypted_data: Base64 encoded encrypted data
        server_name: Server name for key derivation

    Returns:
        Decrypted data
    """
    if not ENCRYPTION_AVAILABLE:
        raise RuntimeError("Encryption dependencies not available")

    key = _get_encryption_key(server_name)
    fernet = Fernet(base64.urlsafe_b64encode(key[:32]))  # Fernet needs 32 bytes

    encrypted = base64.b64decode(encrypted_data.encode())
    decrypted = fernet.decrypt(encrypted)
    return decrypted.decode()


def find_available_port(start_port: int = 8000, max_attempts: int = 100, host: str = "127.0.0.1") -> int:
    """Find an available port starting from the specified port.

    Args:
        start_port: Port to start searching from
        max_attempts: Maximum number of ports to try
        host: Host address to bind to for testing

    Returns:
        An available port number

    Raises:
        RuntimeError: If no available port found within the range
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            continue
    msg = f"Could not find available port in range {start_port}-{start_port + max_attempts}"
    raise RuntimeError(msg)


def is_pid_running(pid: int) -> bool:
    """Check if a process with the given PID is currently running.

    Args:
        pid: Process ID to check

    Returns:
        True if process is running, False otherwise
    """
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_oauth_config_dir() -> Path:
    """Get the configuration directory for storing OAuth tokens and lockfiles.

    Returns:
        Path to the OAuth configuration directory

    The directory is created if it doesn't exist. Uses MCP_OAUTH_CONFIG_DIR
    environment variable if set, otherwise uses the default auth directory.
    """
    # Check for custom OAuth config directory first
    custom_config_dir = os.getenv("MCP_OAUTH_CONFIG_DIR")
    if custom_config_dir:
        config_dir = Path(custom_config_dir).expanduser().absolute()
        # Validate the custom config directory for security
        config_dir = _validate_config_path(config_dir)
    else:
        # Use centralized auth directory utility

        config_dir = get_auth_dir()

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_lockfile_path(server_url_hash: str) -> Path:
    """Get the path to the lockfile for a given server URL hash.

    Args:
        server_url_hash: Hash of the server URL

    Returns:
        Path to the lockfile for the server
    """
    config_dir = get_oauth_config_dir()
    return config_dir / f"auth-{server_url_hash}.lock"


def get_tokens_path(server_url_hash: str, server_name: str | None = None) -> Path:
    """Get the path to the tokens file for a given server URL hash.

    Args:
        server_url_hash: Hash of the server URL
        server_name: Optional server name for organized storage

    Returns:
        Path to the tokens file. Uses server-specific subdirectory if name provided,
        otherwise falls back to legacy hash-based naming.
    """
    config_dir = get_oauth_config_dir()

    # Use server name subdirectory if provided, otherwise fall back to old format
    if server_name:
        # Validate and sanitize server name
        safe_server_name = _validate_server_name(server_name)
        server_dir = config_dir / safe_server_name
        server_dir.mkdir(parents=True, exist_ok=True)
        return server_dir / "tokens.json"
    # Legacy fallback
    return config_dir / f"tokens-{server_url_hash}.json"


def save_tokens(server_url_hash: str, tokens: dict[str, Any], server_name: str | None = None) -> None:
    """Save OAuth tokens to disk with optional encryption.

    Args:
        server_url_hash: Hash of the server URL
        tokens: OAuth token dictionary to save
        server_name: Optional server name for encryption and organized storage

    Encrypts tokens if server name is provided and encryption dependencies are available.
    Falls back to unencrypted storage if encryption fails or is unavailable.
    Sets restrictive file permissions (owner read/write only).
    """
    tokens_path = get_tokens_path(server_url_hash, server_name)

    # Add timestamp when tokens were saved for expiration checking
    tokens_with_timestamp = tokens.copy()
    tokens_with_timestamp["issued_at"] = int(time.time())

    # Try to encrypt if server name is provided and encryption is available
    if server_name and ENCRYPTION_AVAILABLE:
        try:
            safe_server_name = _validate_server_name(server_name)
            token_data = json.dumps(tokens_with_timestamp, indent=2)
            encrypted_data = _encrypt_data(token_data, safe_server_name)

            # Save as encrypted data with metadata
            encrypted_wrapper = {"encrypted": True, "data": encrypted_data, "server_name": safe_server_name}

            with tokens_path.open("w") as f:
                json.dump(encrypted_wrapper, f, indent=2)
        except Exception as e:
            # Fall back to unencrypted storage if encryption fails
            logger = get_logger(__name__, facility="OAUTH")
            logger.warning(
                "Failed to encrypt tokens for server '%s', falling back to unencrypted storage: %s",
                server_name or "UNKNOWN",
                e,
            )
            with tokens_path.open("w") as f:
                json.dump(tokens_with_timestamp, f, indent=2)
    else:
        # Fallback to unencrypted storage
        with tokens_path.open("w") as f:
            json.dump(tokens_with_timestamp, f, indent=2)

    # Set restrictive permissions (owner read/write only)
    tokens_path.chmod(0o600)


def load_tokens(server_url_hash: str, server_name: str | None = None) -> dict[str, Any] | None:
    """Load OAuth tokens from disk with automatic decryption.

    Args:
        server_url_hash: Hash of the server URL
        server_name: Optional server name for decryption

    Returns:
        OAuth token dictionary, or None if not found or decryption fails

    Automatically handles encrypted and unencrypted tokens. Migrates legacy
    token files to new organized structure when server name is provided.
    """
    tokens_path = get_tokens_path(server_url_hash, server_name)

    # If server name provided but file doesn't exist, try legacy format
    if server_name and not tokens_path.exists():
        legacy_path = get_tokens_path(server_url_hash, None)
        if legacy_path.exists():
            # Migrate legacy token file to new location
            try:
                with legacy_path.open() as f:
                    tokens_data = json.load(f)
                save_tokens(server_url_hash, tokens_data, server_name)
                legacy_path.unlink()  # Remove old file after migration
                return tokens_data  # type: ignore[no-any-return]
            except (FileNotFoundError, json.JSONDecodeError):
                pass

    try:
        with tokens_path.open() as f:
            file_data = json.load(f)

        # Check if this is encrypted data
        if isinstance(file_data, dict) and file_data.get("encrypted", False):
            if not ENCRYPTION_AVAILABLE:
                logger = get_logger(__name__, facility="OAUTH")
                logger.warning(
                    "Encrypted tokens found for server '%s' but encryption dependencies not available",
                    server_name or "UNKNOWN",
                )
                return None

            if not server_name:
                logger = get_logger(__name__, facility="OAUTH")
                logger.warning("Encrypted tokens require server name for decryption")
                return None

            try:
                safe_server_name = _validate_server_name(server_name)
                encrypted_data = file_data.get("data")
                stored_server_name = file_data.get("server_name")

                if not encrypted_data:
                    logger = get_logger(__name__, facility="OAUTH")
                    logger.warning("Malformed encrypted token file")
                    return None

                # Validate server name consistency
                if stored_server_name and stored_server_name != safe_server_name:
                    logger = get_logger(__name__, facility="OAUTH")
                    logger.warning(
                        "Server name mismatch in encrypted tokens: expected '%s', found '%s'",
                        safe_server_name,
                        stored_server_name,
                    )
                    # Use stored server name for decryption to handle name changes
                    safe_server_name = stored_server_name

                decrypted_data = _decrypt_data(encrypted_data, safe_server_name)
                parsed_tokens: dict[str, Any] = json.loads(decrypted_data)
                return parsed_tokens
            except Exception as e:
                logger = get_logger(__name__, facility="OAUTH")
                logger.warning(
                    "Failed to decrypt tokens: %s. Token file may be corrupted. "
                    "Expected server: %s, stored server: %s, tokens path: %s",
                    type(e).__name__,
                    safe_server_name if "safe_server_name" in locals() else "unknown",
                    stored_server_name if "stored_server_name" in locals() else "unknown",
                    tokens_path,
                )
                # Remove corrupted token file to prevent repeated failures
                try:
                    tokens_path.unlink()
                    logger.info("Removed corrupted token file: %s", tokens_path)
                except Exception:
                    logger.debug("Failed to remove corrupted token file: %s", tokens_path, exc_info=True)
                return None
        else:
            # Unencrypted data
            if isinstance(file_data, dict):
                return file_data
            return None

    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_client_info(server_url_hash: str, client_info: dict[str, Any], server_name: str | None = None) -> None:
    """Save OAuth client information to disk.

    Args:
        server_url_hash: Hash of the server URL
        client_info: OAuth client information dictionary
        server_name: Optional server name for organized storage

    Sets restrictive file permissions (owner read/write only).
    """
    config_dir = get_oauth_config_dir()

    if server_name:
        # Validate and sanitize server name
        safe_server_name = _validate_server_name(server_name)
        server_dir = config_dir / safe_server_name
        server_dir.mkdir(parents=True, exist_ok=True)
        client_path = server_dir / "client.json"
    else:
        # Legacy fallback
        client_path = config_dir / f"client-{server_url_hash}.json"

    with client_path.open("w") as f:
        json.dump(client_info, f, indent=2)

    # Set restrictive permissions (owner read/write only)
    client_path.chmod(0o600)


def load_client_info(server_url_hash: str, server_name: str | None = None) -> dict[str, Any] | None:
    """Load OAuth client information from disk.

    Args:
        server_url_hash: Hash of the server URL
        server_name: Optional server name for organized storage

    Returns:
        OAuth client information dictionary, or None if not found

    Migrates legacy client files to new organized structure when server name is provided.
    """
    config_dir = get_oauth_config_dir()

    if server_name:
        # Validate and sanitize server name
        safe_server_name = _validate_server_name(server_name)
        client_path = config_dir / safe_server_name / "client.json"
        # If server name provided but file doesn't exist, try legacy format
        if not client_path.exists():
            legacy_path = config_dir / f"client-{server_url_hash}.json"
            if legacy_path.exists():
                # Migrate legacy client file to new location
                try:
                    with legacy_path.open() as f:
                        client_data = json.load(f)
                    save_client_info(server_url_hash, client_data, server_name)
                    legacy_path.unlink()  # Remove old file after migration
                    loaded_client_data: dict[str, Any] = client_data
                    return loaded_client_data
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
    else:
        # Legacy fallback
        client_path = config_dir / f"client-{server_url_hash}.json"

    try:
        with client_path.open() as f:
            final_client_data: dict[str, Any] = json.load(f)
            return final_client_data
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_code_verifier(server_url_hash: str, code_verifier: str, server_name: str | None = None) -> None:
    """Save PKCE code verifier to disk.

    Args:
        server_url_hash: Hash of the server URL
        code_verifier: PKCE code verifier string
        server_name: Optional server name for organized storage

    Sets restrictive file permissions (owner read/write only).
    """
    config_dir = get_oauth_config_dir()

    if server_name:
        # Validate and sanitize server name
        safe_server_name = _validate_server_name(server_name)
        server_dir = config_dir / safe_server_name
        server_dir.mkdir(parents=True, exist_ok=True)
        verifier_path = server_dir / "verifier.txt"
    else:
        # Legacy fallback
        verifier_path = config_dir / f"verifier-{server_url_hash}.txt"

    with verifier_path.open("w") as f:
        f.write(code_verifier)

    # Set restrictive permissions (owner read/write only)
    verifier_path.chmod(0o600)


def load_code_verifier(server_url_hash: str, server_name: str | None = None) -> str | None:
    """Load PKCE code verifier from disk.

    Args:
        server_url_hash: Hash of the server URL
        server_name: Optional server name for organized storage

    Returns:
        PKCE code verifier string, or None if not found

    Migrates legacy verifier files to new organized structure when server name is provided.
    """
    config_dir = get_oauth_config_dir()

    if server_name:
        # Validate and sanitize server name
        safe_server_name = _validate_server_name(server_name)
        verifier_path = config_dir / safe_server_name / "verifier.txt"
        # If server name provided but file doesn't exist, try legacy format
        if not verifier_path.exists():
            legacy_path = config_dir / f"verifier-{server_url_hash}.txt"
            if legacy_path.exists():
                # Migrate legacy verifier file to new location
                try:
                    with legacy_path.open() as f:
                        verifier_data = f.read().strip()
                    save_code_verifier(server_url_hash, verifier_data, server_name)
                    legacy_path.unlink()  # Remove old file after migration
                    return verifier_data
                except FileNotFoundError:
                    pass
    else:
        # Legacy fallback
        verifier_path = config_dir / f"verifier-{server_url_hash}.txt"

    try:
        with verifier_path.open() as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def cleanup_auth_files(server_url_hash: str, server_name: str | None = None) -> None:
    """Clean up all authentication-related files for a server.

    Args:
        server_url_hash: Hash of the server URL
        server_name: Optional server name

    Removes tokens, client info, code verifier, and lockfiles.
    Handles both new organized structure and legacy file naming.
    """
    config_dir = get_oauth_config_dir()

    files_to_remove = []

    if server_name:
        # Validate and sanitize server name
        safe_server_name = _validate_server_name(server_name)

        # Clean up server-specific directory
        server_dir = config_dir / safe_server_name
        if server_dir.exists():
            with contextlib.suppress(OSError):
                shutil.rmtree(server_dir)

        # Also clean up legacy files
        files_to_remove.extend(
            [
                config_dir / f"tokens-{server_url_hash}.json",
                config_dir / f"client-{server_url_hash}.json",
                config_dir / f"verifier-{server_url_hash}.txt",
            ]
        )
    else:
        # Legacy cleanup
        files_to_remove.extend(
            [
                get_tokens_path(server_url_hash),
                config_dir / f"client-{server_url_hash}.json",
                config_dir / f"verifier-{server_url_hash}.txt",
            ]
        )

    files_to_remove.append(get_lockfile_path(server_url_hash))

    for file_path in files_to_remove:
        with contextlib.suppress(FileNotFoundError):
            file_path.unlink()


class FileLock:
    """Simple file-based locking mechanism."""

    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self.lock_fd: int | None = None

    def acquire(self, timeout: float = 10.0) -> bool:
        """Acquire the lock with optional timeout."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                lock_fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                self.lock_fd = lock_fd
                # Write current PID to lock file
                os.write(lock_fd, str(os.getpid()).encode())
                return True
            except FileExistsError:
                time.sleep(0.1)

        # Timeout reached without acquiring lock
        return False

    def release(self) -> None:
        """Release the lock."""
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
            with contextlib.suppress(FileNotFoundError):
                self.lock_file.unlink()

    def __enter__(self) -> "FileLock":
        """Enter the runtime context, acquiring the lock."""
        if not self.acquire():
            msg = f"Could not acquire lock: {self.lock_file}"
            raise RuntimeError(msg)
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Exit the runtime context, releasing the lock."""
        self.release()


def setup_signal_handlers(cleanup_func: Callable[[], None]) -> None:
    """Setup signal handlers for graceful shutdown.

    Args:
        cleanup_func: Function to call for cleanup before exit

    Sets up SIGINT and SIGTERM handlers that call the cleanup function
    and then exit the process.
    """

    def signal_handler(signum: int, frame: Any) -> None:
        cleanup_func()
        # Use os._exit() to avoid SystemExit exception and cleanup tracebacks
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def clear_tokens(server_url_hash: str, server_name: str | None = None) -> None:
    """Clear OAuth tokens for a specific server.

    Args:
        server_url_hash: Hash of the server URL
        server_name: Optional server name
    """
    cleanup_auth_files(server_url_hash, server_name)


def clear_all_tokens() -> None:
    """Clear all OAuth tokens for all servers."""
    config_dir = get_oauth_config_dir()

    if not config_dir.exists():
        return

    # Remove all server-specific directories
    for item in config_dir.iterdir():
        if item.is_dir():
            with contextlib.suppress(OSError):
                shutil.rmtree(item)

    # Remove any legacy files in the root config directory
    for pattern in ["tokens-*.json", "client-*.json", "verifier-*.txt", "*.lock"]:
        for file_path in config_dir.glob(pattern):
            with contextlib.suppress(FileNotFoundError):
                file_path.unlink()
