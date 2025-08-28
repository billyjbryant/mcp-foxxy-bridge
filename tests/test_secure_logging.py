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

"""Test for secure logging utilities to ensure sensitive data is properly redacted."""

from mcp_foxxy_bridge.utils.logging import (
    mask_authentication_config,
    mask_authorization_header,
    mask_oauth_tokens,
    mask_query_parameters,
    redact_url_credentials,
    safe_log_headers,
    safe_log_server_name,
)


class TestSecureLogging:
    """Test secure logging utilities to ensure sensitive data is properly redacted."""

    def test_mask_authorization_header(self):
        """Test masking of Authorization headers."""
        # Test Bearer token
        original = "Bearer abc123def456ghi789"
        masked = mask_authorization_header(original)
        assert masked.startswith("Bearer abc123def456")
        assert "..." in masked
        assert masked.endswith("789")
        # Should not contain the full original token
        assert "abc123def456ghi789" not in masked

        # Test Basic auth
        masked = mask_authorization_header("Basic dXNlcjpwYXNzd29yZA==")
        assert masked.startswith("Basic")
        assert "..." in masked

        # Test short token (should be fully redacted)
        masked = mask_authorization_header("Bearer short")
        assert masked == "Bearer [REDACTED]"

        # Test empty/invalid input
        assert mask_authorization_header("") == "[EMPTY_AUTH_HEADER]"
        assert mask_authorization_header("invalid") == "[REDACTED_AUTH_HEADER]"

    def test_mask_oauth_tokens(self):
        """Test masking of OAuth token information."""
        tokens = {
            "access_token": "abcdefghijklmnop",
            "refresh_token": "refresh123456789",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write",
        }

        masked = mask_oauth_tokens(tokens)

        # Sensitive fields should be masked
        assert masked["access_token"] == "abc...nop"
        assert masked["refresh_token"] == "[REDACTED]"

        # Non-sensitive fields should remain
        assert masked["token_type"] == "Bearer"
        assert masked["expires_in"] == 3600
        assert masked["scope"] == "read write"

    def test_mask_query_parameters(self):
        """Test masking of query parameters."""
        params = {
            "code": "authorization_code_123",
            "state": "state_value_456",
            "error": "access_denied",
            "error_description": "User denied access",
        }

        masked = mask_query_parameters(params)

        # Highly sensitive should be fully redacted
        assert masked["code"] == "[REDACTED]"

        # Moderately sensitive should be partially shown
        assert "sta" in masked["state"]
        assert "456" in masked["state"]
        assert "..." in masked["state"]

        # Non-sensitive should remain
        assert masked["error"] == "access_denied"
        assert masked["error_description"] == "User denied access"

    def test_mask_authentication_config(self):
        """Test masking of authentication configuration."""
        config = {
            "type": "basic",
            "username": "testuser",
            "password": "secret123",
            "api_key": "apikey456",
            "timeout": 30,
        }

        masked = mask_authentication_config(config)

        # Sensitive fields should be redacted
        assert masked["password"] == "[REDACTED]"
        assert masked["api_key"] == "[REDACTED]"

        # Non-sensitive fields should remain
        assert masked["type"] == "basic"
        assert masked["username"] == "testuser"
        assert masked["timeout"] == 30

    def test_redact_url_credentials(self):
        """Test redacting credentials from URLs."""
        url = "https://user:password@example.com/path?query=value"
        redacted = redact_url_credentials(url)

        assert "[REDACTED]" in redacted
        assert "user" not in redacted
        assert "password" not in redacted
        assert "example.com" in redacted
        assert "/path?query=value" in redacted

    def test_safe_log_headers(self):
        """Test safe logging of HTTP headers."""
        headers = {
            "Authorization": "Bearer secret_token",
            "X-API-Key": "api_secret",
            "User-Agent": "MCP-Bridge/1.0",
            "Content-Type": "application/json",
            "X-Custom-Token": "custom_secret",
        }

        safe = safe_log_headers(headers)

        # Sensitive headers should be redacted
        assert safe["Authorization"] == "[REDACTED]"
        assert safe["X-API-Key"] == "[REDACTED]"
        assert safe["X-Custom-Token"] == "[REDACTED]"

        # Non-sensitive headers should remain
        assert safe["User-Agent"] == "MCP-Bridge/1.0"
        assert safe["Content-Type"] == "application/json"

    def test_error_handling(self):
        """Test error handling for invalid inputs."""
        # Test with None/invalid inputs
        assert mask_oauth_tokens(None)["error"] == "[INVALID_TOKEN_FORMAT]"
        assert mask_query_parameters("invalid")["error"] == "[INVALID_PARAMS_FORMAT]"
        assert mask_authentication_config([])["error"] == "[INVALID_AUTH_CONFIG]"
        assert redact_url_credentials(123) == "[INVALID_URL]"
        assert safe_log_headers("invalid")["error"] == "[INVALID_HEADERS]"

    def test_safe_log_server_name(self):
        """Test safe_log_server_name function."""
        # Test normal server names
        assert safe_log_server_name("filesystem") == "[SERVER_NAME]"
        assert safe_log_server_name("oauth-server-production") == "[SERVER_NAME]"

        # Test with show_partial flag
        assert safe_log_server_name("filesystem", show_partial=True) == "fil...tem"
        assert safe_log_server_name("oauth-server-production", show_partial=True) == "oau...ion"

        # Test short names with show_partial
        assert safe_log_server_name("test", show_partial=True) == "[SERVER_NAME]"

        # Test edge cases
        assert safe_log_server_name("") == "[EMPTY_SERVER_NAME]"
        assert safe_log_server_name("   ") == "[EMPTY_SERVER_NAME]"
        assert safe_log_server_name(None) == "[INVALID_SERVER_NAME]"
        assert safe_log_server_name(123) == "[INVALID_SERVER_NAME]"
