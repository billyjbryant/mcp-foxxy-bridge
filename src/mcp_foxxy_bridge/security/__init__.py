# MCP Foxxy Bridge - Security Module
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
"""Security and access control for MCP tools and resources."""

from .classifier import ToolClassifier, ToolType
from .config import BridgeSecurityConfig, ServerSecurityConfig, ToolSecurityConfig
from .controller import AccessController
from .patterns import PatternMatcher
from .policy import SecurityPolicy

__all__ = [
    "AccessController",
    "BridgeSecurityConfig",
    "PatternMatcher",
    "SecurityPolicy",
    "ServerSecurityConfig",
    "ToolClassifier",
    "ToolSecurityConfig",
    "ToolType",
]
