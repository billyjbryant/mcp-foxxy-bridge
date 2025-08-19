#
# MCP Foxxy Bridge - String Utilities
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
r"""String Manipulation and Validation Utilities.

This module provides various string processing utilities commonly needed
throughout the MCP Foxxy Bridge system, including normalization,
validation, and formatting functions.

Key Features:
    - Name normalization for URLs and identifiers
    - String validation (identifiers, names, etc.)
    - Safe string truncation with ellipsis
    - Filename sanitization for cross-platform compatibility
    - Case conversion utilities

Example:
    Basic string operations:

    >>> normalize_name("My Server Name")
    'my_server_name'
    >>> sanitize_filename("file/with\\bad:chars")
    'file_with_bad_chars'
    >>> truncate_string("Very long text...", 10)
    'Very lo...'
"""

import re


def normalize_name(name: str) -> str:
    """Normalize a name for use as URL-safe identifier.

    Converts names to lowercase, replaces spaces and special characters
    with underscores, and ensures the result is suitable for URLs and
    file systems.

    Args:
        name: The original name to normalize

    Returns:
        Normalized name suitable for URLs and identifiers

    Example:
        >>> normalize_name("File System Server")
        'file_system_server'
        >>> normalize_name("GitHub API v2")
        'github_api_v2'
        >>> normalize_name("My-Special_Server!")
        'my_special_server'
    """
    if not name:
        return "unnamed"

    # Convert to lowercase
    normalized = name.lower()

    # Replace spaces, hyphens, and other non-alphanumeric chars with underscores
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)

    # Remove leading/trailing underscores
    normalized = normalized.strip("_")

    # Ensure we don't have empty string or just underscores
    if not normalized or normalized == "_":
        normalized = "unnamed"

    # Limit length to reasonable size
    if len(normalized) > 50:
        normalized = normalized[:50].rstrip("_")

    return normalized


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    r"""Sanitize a filename for cross-platform compatibility.

    Removes or replaces characters that are invalid in filenames
    on various operating systems.

    Args:
        filename: The original filename
        replacement: Character to use as replacement for invalid chars

    Returns:
        Sanitized filename safe for all platforms

    Example:
        >>> sanitize_filename("file/with\\bad:chars")
        'file_with_bad_chars'
        >>> sanitize_filename("document<>name", replacement="-")
        'document--name'
    """
    if not filename:
        return "untitled"

    # Characters that are invalid in filenames on various platforms
    invalid_chars = r'<>:"/\\|?*'

    # Replace invalid characters
    sanitized = filename
    for char in invalid_chars:
        sanitized = sanitized.replace(char, replacement)

    # Remove control characters
    sanitized = "".join(char for char in sanitized if ord(char) >= 32)

    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(". ")

    # Ensure not empty
    if not sanitized:
        sanitized = "untitled"

    # Limit length (most filesystems support 255 chars)
    if len(sanitized) > 200:
        sanitized = sanitized[:200]

    return sanitized


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to maximum length with optional suffix.

    Safely truncates strings while preserving word boundaries when
    possible and adding an ellipsis or other suffix.

    Args:
        text: The text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating

    Returns:
        Truncated string with suffix if needed

    Example:
        >>> truncate_string("This is a very long sentence", 15)
        'This is a ve...'
        >>> truncate_string("Short text", 20)
        'Short text'
        >>> truncate_string("Long text here", 10, suffix="…")
        'Long tex…'
    """
    if not text:
        return text

    if len(text) <= max_length:
        return text

    if max_length <= len(suffix):
        # If max_length is too small, just return truncated text without suffix
        return text[:max_length]

    # Calculate available space for text
    available_length = max_length - len(suffix)

    # Try to truncate at word boundary
    truncated = text[:available_length]

    # Look for last space to avoid cutting words in half
    last_space = truncated.rfind(" ")
    if last_space > available_length // 2:  # Only use word boundary if it's not too far back
        truncated = truncated[:last_space]

    return truncated + suffix


def is_valid_identifier(name: str) -> bool:
    """Check if string is a valid identifier (variable name, etc.).

    Validates that the string follows the rules for valid identifiers
    in most programming languages (starts with letter/underscore,
    contains only letters, digits, underscores).

    Args:
        name: The string to validate

    Returns:
        True if the string is a valid identifier

    Example:
        >>> is_valid_identifier("valid_name")
        True
        >>> is_valid_identifier("123invalid")
        False
        >>> is_valid_identifier("name-with-dashes")
        False
    """
    if not name:
        return False

    # Must start with letter or underscore
    if not (name[0].isalpha() or name[0] == "_"):
        return False

    # Must contain only letters, digits, underscores
    return all(char.isalnum() or char == "_" for char in name)


def is_valid_server_name(name: str) -> bool:
    """Check if string is a valid server name.

    Server names must be suitable for use in URLs and configuration
    keys. They can contain letters, digits, underscores, and hyphens.

    Args:
        name: The server name to validate

    Returns:
        True if the name is valid for a server

    Example:
        >>> is_valid_server_name("filesystem")
        True
        >>> is_valid_server_name("github-api")
        True
        >>> is_valid_server_name("server with spaces")
        False
    """
    if not name:
        return False

    # Must contain only letters, digits, underscores, hyphens
    return re.match(r"^[a-zA-Z0-9_-]+$", name) is not None


def camel_to_snake(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case.

    Args:
        name: The camelCase or PascalCase string

    Returns:
        snake_case version of the string

    Example:
        >>> camel_to_snake("camelCaseString")
        'camel_case_string'
        >>> camel_to_snake("PascalCaseString")
        'pascal_case_string'
    """
    if not name:
        return name

    # Insert underscore before uppercase letters (except at start)
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name)

    # Convert to lowercase
    return snake.lower()


def snake_to_camel(name: str, pascal_case: bool = False) -> str:
    """Convert snake_case to camelCase or PascalCase.

    Args:
        name: The snake_case string
        pascal_case: If True, use PascalCase; otherwise camelCase

    Returns:
        camelCase or PascalCase version of the string

    Example:
        >>> snake_to_camel("snake_case_string")
        'snakeCaseString'
        >>> snake_to_camel("snake_case_string", pascal_case=True)
        'SnakeCaseString'
    """
    if not name:
        return name

    components = name.split("_")

    if pascal_case:
        # Capitalize all components
        return "".join(word.capitalize() for word in components)
    # Capitalize all but first component
    if len(components) == 1:
        return components[0].lower()
    return components[0].lower() + "".join(word.capitalize() for word in components[1:])


def pluralize(word: str) -> str:  # Pluralization rules need many returns
    """Simple English pluralization.

    Args:
        word: The singular word to pluralize

    Returns:
        Plural form of the word

    Example:
        >>> pluralize("server")
        'servers'
        >>> pluralize("proxy")
        'proxies'
        >>> pluralize("child")
        'children'
    """
    if not word:
        return word

    word = word.lower()

    # Special cases
    special_cases = {
        "child": "children",
        "person": "people",
        "man": "men",
        "woman": "women",
        "foot": "feet",
        "tooth": "teeth",
        "mouse": "mice",
        "goose": "geese",
    }

    if word in special_cases:
        return special_cases[word]

    # Regular rules
    if word.endswith(("s", "sh", "ch", "x", "z")):
        return word + "es"
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith("f"):
        return word[:-1] + "ves"
    if word.endswith("fe"):
        return word[:-2] + "ves"
    return word + "s"


def escape_for_shell(text: str) -> str:
    r"""Escape string for safe use in shell commands.

    Args:
        text: The text to escape

    Returns:
        Shell-escaped version of the text

    Example:
        >>> escape_for_shell("text with spaces")
        "'text with spaces'"
        >>> escape_for_shell("text'with'quotes")
        "'text'\"'\"'with'\"'\"'quotes'"
    """
    if not text:
        return "''"

    # If text is simple (alphanumeric, underscore, hyphen, dot), no escaping needed
    if re.match(r"^[a-zA-Z0-9._-]+$", text):
        return text

    # Otherwise, wrap in single quotes and escape any single quotes
    return "'" + text.replace("'", "'\"'\"'") + "'"


def strip_ansi_codes(text: str) -> str:
    r"""Remove ANSI color codes and escape sequences from text.

    Args:
        text: Text that may contain ANSI codes

    Returns:
        Text with ANSI codes removed

    Example:
        >>> strip_ansi_codes("\\033[31mRed text\\033[0m")
        'Red text'
    """
    if not text:
        return text

    # Remove ANSI escape sequences
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def normalize_whitespace(text: str) -> str:
    r"""Normalize whitespace in text.

    Replaces multiple consecutive whitespace characters with single spaces
    and strips leading/trailing whitespace.

    Args:
        text: Text to normalize

    Returns:
        Text with normalized whitespace

    Example:
        >>> normalize_whitespace("  text   with\\tmultiple\\n  spaces  ")
        'text with multiple spaces'
    """
    if not text:
        return text

    # Replace any whitespace sequence with single space
    normalized = re.sub(r"\s+", " ", text)

    # Strip leading/trailing whitespace
    return normalized.strip()


def format_bytes(num_bytes: int, binary: bool = True) -> str:
    """Format byte count as human-readable string.

    Args:
        num_bytes: Number of bytes
        binary: If True, use binary units (1024); otherwise decimal (1000)

    Returns:
        Formatted byte string

    Example:
        >>> format_bytes(1024)
        '1.0 KiB'
        >>> format_bytes(1000, binary=False)
        '1.0 KB'
    """
    if num_bytes == 0:
        return "0 B"

    if binary:
        units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        divisor = 1024.0
    else:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        divisor = 1000.0

    size = float(num_bytes)
    unit_index = 0

    while size >= divisor and unit_index < len(units) - 1:
        size /= divisor
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"
