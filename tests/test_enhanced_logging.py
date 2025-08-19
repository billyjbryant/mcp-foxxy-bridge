"""Tests for new v1.2.0 logging features."""

import logging
from unittest.mock import MagicMock, patch

from rich.console import Console

from mcp_foxxy_bridge.utils.logging_config import (
    MCPRichHandler,
    setup_rich_logging,
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
        setup_rich_logging(debug=True)

        # Check root logger configuration
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], MCPRichHandler)

    def test_setup_rich_logging_normal_mode(self) -> None:
        """Test setup_rich_logging in normal mode."""
        setup_rich_logging(debug=False)

        # Check root logger configuration
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], MCPRichHandler)

    def test_uvicorn_logger_configuration(self) -> None:
        """Test that uvicorn loggers are properly configured."""
        setup_rich_logging(debug=True)

        # Check uvicorn loggers
        uvicorn_logger = logging.getLogger("uvicorn")
        assert uvicorn_logger.level == logging.INFO
        assert not uvicorn_logger.propagate
        assert len(uvicorn_logger.handlers) == 1
        assert isinstance(uvicorn_logger.handlers[0], MCPRichHandler)

    def test_mcp_logger_configuration(self) -> None:
        """Test that MCP loggers are properly configured."""
        setup_rich_logging(debug=True)

        # Check MCP loggers
        mcp_logger = logging.getLogger("mcp")
        assert mcp_logger.level == logging.WARNING
        assert not mcp_logger.propagate

        mcp_server_logger = logging.getLogger("mcp.server")
        assert mcp_server_logger.level == logging.INFO  # Debug mode
        assert not mcp_server_logger.propagate

    @patch("mcp_foxxy_bridge.utils.logging_config.Console")
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
