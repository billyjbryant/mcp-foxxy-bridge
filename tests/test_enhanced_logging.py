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

"""Tests for new v1.2.0 logging features."""

import logging
from unittest.mock import MagicMock, patch

from rich.console import Console

from mcp_foxxy_bridge.utils.logging import (
    MCPRichHandler,
    setup_logging,
)


class TestEnhancedLogging:
    """Test cases for enhanced logging features."""

    def teardown_method(self) -> None:
        """Clean up logging configuration after each test."""
        # Reset root logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.WARNING)

    def test_mcp_rich_handler_initialization(self) -> None:
        """Test MCPRichHandler initialization."""
        handler = MCPRichHandler()

        assert handler.console is not None
        assert isinstance(handler.console, Console)

    def test_setup_rich_logging_debug_mode(self) -> None:
        """Test setup_rich_logging in debug mode."""
        setup_logging(debug=True)

        # Check root logger configuration
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert len(root_logger.handlers) == 2  # Console + file handler
        handler_types = [type(h).__name__ for h in root_logger.handlers]
        assert "MCPRichHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

    def test_setup_rich_logging_normal_mode(self) -> None:
        """Test setup_rich_logging in normal mode."""
        setup_logging(debug=False)

        # Check root logger configuration
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) == 2  # Console + file handler
        handler_types = [type(h).__name__ for h in root_logger.handlers]
        assert "MCPRichHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

    def test_uvicorn_logger_configuration(self) -> None:
        """Test that uvicorn loggers are properly configured."""
        setup_logging(debug=True)

        # Check uvicorn loggers
        uvicorn_logger = logging.getLogger("uvicorn")
        assert uvicorn_logger.level == logging.INFO
        assert not uvicorn_logger.propagate
        assert len(uvicorn_logger.handlers) == 1
        assert isinstance(uvicorn_logger.handlers[0], MCPRichHandler)

    def test_mcp_logger_configuration(self) -> None:
        """Test that MCP loggers are properly configured."""
        setup_logging(debug=True)

        # Check MCP loggers
        mcp_logger = logging.getLogger("mcp")
        assert mcp_logger.level == logging.WARNING
        assert not mcp_logger.propagate

        mcp_server_logger = logging.getLogger("mcp.server")
        assert mcp_server_logger.level == logging.INFO  # Debug mode
        assert not mcp_server_logger.propagate

    @patch("mcp_foxxy_bridge.utils.logging.Console")
    def test_rich_console_configuration(self, mock_console_class: MagicMock) -> None:
        """Test Rich console configuration."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        MCPRichHandler()

        # Verify console was configured correctly
        mock_console_class.assert_called_with(
            stderr=True,
            force_terminal=True,
            width=120,
        )
