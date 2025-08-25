"""Path security utilities for preventing path traversal attacks.

This module provides functions to safely validate and sanitize file paths
to prevent directory traversal and other path-based security vulnerabilities.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PathTraversalError(ValueError):
    """Raised when a path traversal attempt is detected."""

    def __init__(self, path: str, message: str = "Path traversal detected") -> None:
        super().__init__(f"{message}: {path}")
        self.path = path


def validate_safe_path(
    user_path: str | Path,
    allowed_base_dirs: list[str | Path] | None = None,
    must_be_relative_to_base: bool = True,
    allowed_extensions: list[str] | None = None,
    max_path_length: int = 4096,
) -> Path:
    """Validate and sanitize a user-provided path to prevent traversal attacks.

    Args:
        user_path: The user-provided path to validate
        allowed_base_dirs: List of directories that paths must be within.
                          If None, allows any path under user's config directory
        must_be_relative_to_base: If True, path must be within allowed_base_dirs
        allowed_extensions: List of allowed file extensions (including dot)
        max_path_length: Maximum allowed path length

    Returns:
        Path: A validated, absolute Path object

    Raises:
        PathTraversalError: If path traversal is detected
        ValueError: If path is invalid or not allowed
    """
    if not user_path:
        raise ValueError("Path cannot be empty")

    # Convert to string for validation
    path_str = str(user_path)

    # Check path length
    if len(path_str) > max_path_length:
        raise ValueError(f"Path too long: {len(path_str)} > {max_path_length}")

    # Check for null bytes (directory traversal attempt)
    if "\x00" in path_str:
        raise PathTraversalError(path_str, "Null byte detected in path")

    # Check for directory traversal patterns BEFORE resolving the path
    if ".." in path_str:
        raise PathTraversalError(path_str, "Directory traversal sequence detected")

    # Check for other suspicious patterns
    suspicious_patterns = ["$", "~/../"]
    for pattern in suspicious_patterns:
        if pattern in path_str:
            raise PathTraversalError(path_str, f"Suspicious pattern detected: {pattern}")

    # Convert to Path and resolve to absolute path
    try:
        path = Path(path_str).expanduser().resolve()
    except (OSError, ValueError) as e:
        raise ValueError(f"Invalid path: {path_str}") from e

    # Validate file extension if specified
    if allowed_extensions:
        if path.suffix.lower() not in [ext.lower() for ext in allowed_extensions]:
            raise ValueError(f"File extension not allowed: {path.suffix}")

    # Validate against allowed base directories
    if must_be_relative_to_base and allowed_base_dirs:
        allowed_bases = [Path(base).expanduser().resolve() for base in allowed_base_dirs]

        # Check if path is within any allowed base directory
        is_allowed = False
        for base in allowed_bases:
            try:
                # This will raise ValueError if path is not relative to base
                path.relative_to(base)
                is_allowed = True
                break
            except ValueError:
                continue

        if not is_allowed:
            allowed_str = ", ".join(str(base) for base in allowed_bases)
            raise PathTraversalError(path_str, f"Path not within allowed directories: {allowed_str}")

    return path


def validate_config_path(user_path: str | Path, config_base_dir: Path) -> Path:
    """Validate a configuration file path.

    Args:
        user_path: User-provided config file path
        config_base_dir: Base configuration directory

    Returns:
        Path: Validated configuration file path

    Raises:
        PathTraversalError: If path traversal is detected
        ValueError: If path is invalid
    """
    return validate_safe_path(
        user_path,
        allowed_base_dirs=[config_base_dir, config_base_dir.parent],
        must_be_relative_to_base=True,
        allowed_extensions=[".json"],
        max_path_length=1024,
    )


def validate_config_dir(user_path: str | Path) -> Path:
    """Validate a configuration directory path.

    Args:
        user_path: User-provided config directory path

    Returns:
        Path: Validated configuration directory path

    Raises:
        PathTraversalError: If path traversal is detected
        ValueError: If path is invalid
    """
    # Check for basic traversal attacks but allow user to specify config dirs
    path_str = str(user_path)

    # Check for null bytes
    if "\x00" in path_str:
        raise PathTraversalError(path_str, "Null byte detected in path")

    # Check for directory traversal patterns
    if ".." in path_str:
        raise PathTraversalError(path_str, "Directory traversal sequence detected")

    # Convert to absolute path
    try:
        path = Path(path_str).expanduser().resolve()
    except (OSError, ValueError) as e:
        raise ValueError(f"Invalid path: {path_str}") from e

    # Ensure it's actually a directory or can be created
    if path.exists() and not path.is_dir():
        raise ValueError(f"Path exists but is not a directory: {path}")

    return path


def safe_write_file(file_path: Path, content: str, allowed_base_dirs: list[str | Path]) -> None:
    """Safely write content to a file after validating the path.

    Args:
        file_path: Path to write to (must be pre-validated)
        content: Content to write
        allowed_base_dirs: Directories that the file must be within

    Raises:
        PathTraversalError: If final validation fails
        OSError: If file cannot be written
    """
    # Final validation before writing
    validate_safe_path(
        file_path,
        allowed_base_dirs=allowed_base_dirs,
        must_be_relative_to_base=True,
    )

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file with restricted permissions
    with file_path.open("w", encoding="utf-8") as f:
        f.write(content)

    # Set restrictive permissions (owner read/write only)
    try:
        file_path.chmod(0o600)
    except OSError:
        logger.warning("Could not set restrictive permissions on %s", file_path)
