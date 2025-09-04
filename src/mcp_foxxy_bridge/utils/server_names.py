#
# MCP Foxxy Bridge - Server Name Utilities
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
"""Server name utilities for case-insensitive matching."""

from typing import Any


def normalize_server_name(name: str) -> str:
    """Normalize server name to lowercase for case-insensitive matching."""
    return name.lower()


def find_server_key(servers: dict[str, Any], target_name: str) -> str | None:
    """Find actual server key using case-insensitive matching."""
    normalized_target = normalize_server_name(target_name)
    for key in servers:
        if normalize_server_name(key) == normalized_target:
            return key
    return None
