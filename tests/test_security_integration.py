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

"""Integration security tests for MCP Foxxy Bridge.

This module provides end-to-end integration tests for security features
including configuration loading, token management, and command execution
in realistic scenarios.
"""

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from mcp_foxxy_bridge.config.config_loader import (
    ConfigLoader,
    expand_env_vars,
    load_bridge_config_from_file,
)
from mcp_foxxy_bridge.oauth import utils as oauth_utils


class TestConfigurationSecurity:
    """Test security in configuration loading scenarios."""

    def test_config_with_environment_variables_only(self) -> None:
        """Test configuration loading with only environment variables (no command substitution)."""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "python",
                    "args": ["-m", "server"],
                    "env": {"API_KEY": "${API_SECRET}", "DATABASE_URL": "${DB_URL:sqlite:///default.db}"},
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f, indent=2)
            config_file = f.name

        try:
            with patch.dict(os.environ, {"API_SECRET": "secret123", "DB_URL": "postgresql://localhost"}):
                config = load_bridge_config_from_file(config_file, {})

                server = config.servers["test-server"]
                assert server.env is not None, "Server env should not be None"
                assert server.env["API_KEY"] == "secret123"
                assert server.env["DATABASE_URL"] == "postgresql://localhost"
        finally:
            Path(config_file).unlink()

    def test_config_with_disabled_command_substitution(self) -> None:
        """Test that command substitution is left unchanged when disabled."""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "python",
                    "args": ["$(echo dangerous_command)"],
                    "env": {"TOKEN": "$(vault read -field=token secret/api)", "SAFE_VAR": "${SAFE_VALUE:default}"},
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f, indent=2)
            config_file = f.name

        try:
            # Command substitution disabled by default
            with patch.dict(os.environ, {"SAFE_VALUE": "safe123"}, clear=True):
                config = load_bridge_config_from_file(config_file, {})

                server = config.servers["test-server"]
                # Command substitution should be left unchanged
                assert server.args is not None, "Server args should not be None"
                assert server.args[0] == "$(echo dangerous_command)"
                assert server.env is not None, "Server env should not be None"
                assert server.env["TOKEN"] == "$(vault read -field=token secret/api)"
                # Environment variables should still work
                assert server.env["SAFE_VAR"] == "safe123"
        finally:
            Path(config_file).unlink()

    def test_config_with_enabled_command_substitution_safe_commands(self) -> None:
        """Test command substitution with safe commands when explicitly enabled."""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "python",
                    "args": ["-m", "server"],
                    "env": {"CURRENT_USER": "$(whoami)", "TIMESTAMP": "$(date +%Y-%m-%d)", "HOSTNAME": "$(hostname)"},
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f, indent=2)
            config_file = f.name

        try:
            with patch.dict(os.environ, {"MCP_ALLOW_COMMAND_SUBSTITUTION": "true"}):
                config = load_bridge_config_from_file(config_file, {})

                server = config.servers["test-server"]
                # These should have been executed
                assert server.env is not None, "Server env should not be None"
                assert server.env["CURRENT_USER"] != "$(whoami)"
                assert server.env["TIMESTAMP"] != "$(date +%Y-%m-%d)"
                assert server.env["HOSTNAME"] != "$(hostname)"

                # Verify they're actual values
                assert len(server.env["CURRENT_USER"]) > 0
                assert len(server.env["TIMESTAMP"]) > 0
                assert len(server.env["HOSTNAME"]) > 0
        finally:
            Path(config_file).unlink()

    def test_config_with_dangerous_command_substitution(self) -> None:
        """Test that dangerous command substitution is blocked even when enabled."""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "python",
                    "args": ["-m", "server"],
                    "env": {"DANGEROUS": "$(rm -rf /tmp/test)"},
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f, indent=2)
            config_file = f.name

        try:
            with patch.dict(os.environ, {"MCP_ALLOW_COMMAND_SUBSTITUTION": "true"}):
                config = load_bridge_config_from_file(config_file, {})

                server = config.servers["test-server"]
                # Dangerous command should be left unchanged (failed to execute)
                assert server.env is not None, "Server env should not be None"
                assert server.env["DANGEROUS"] == "$(rm -rf /tmp/test)"
        finally:
            Path(config_file).unlink()

    def test_config_loader_validation(self) -> None:
        """Test ConfigLoader validation functionality."""
        config_data = {"mcpServers": {"valid-server": {"command": "python", "args": ["-m", "server"]}}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f, indent=2)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file)
            errors = loader.validate_config()
            assert len(errors) == 0  # Should be valid

            # Test loading works
            config = loader.load_config()
            assert "valid-server" in config.servers
        finally:
            Path(config_file).unlink()

    def test_config_validation_with_invalid_data(self) -> None:
        """Test configuration validation catches security issues."""
        # Invalid config with missing required fields
        invalid_config = {
            "mcpServers": {
                "invalid-server": {
                    # Missing required 'command' field
                    "args": ["-m", "server"]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(invalid_config, f, indent=2)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file)
            errors = loader.validate_config()
            # Should have validation errors due to missing command
            assert len(errors) > 0
        finally:
            Path(config_file).unlink()


class TestOAuthIntegrationSecurity:
    """Test OAuth security in integration scenarios."""

    @patch("mcp_foxxy_bridge.oauth.utils.keyring")
    @patch("mcp_foxxy_bridge.oauth.utils.ENCRYPTION_AVAILABLE", new=True)
    def test_complete_oauth_flow_with_encryption(self, mock_keyring: Any) -> None:
        """Test complete OAuth flow with encryption enabled."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("mcp_foxxy_bridge.oauth.utils.get_config_dir") as mock_get_config,
        ):
            config_dir = Path(temp_dir) / "auth"
            config_dir.mkdir(parents=True)
            mock_get_config.return_value = config_dir

            # Mock encryption key
            test_key = os.urandom(32)
            encoded_key = base64.b64encode(test_key).decode()
            mock_keyring.get_password.return_value = encoded_key
            mock_keyring.set_password.return_value = None

            server_name = "github-api"
            server_url_hash = "gh123456"

            # Simulate OAuth flow data
            client_info = {
                "client_id": "github_client_123",
                "client_secret": "github_secret_456",
                "redirect_uri": "http://localhost:8090/callback",
            }

            tokens = {
                "access_token": "gho_1234567890abcdef",
                "refresh_token": "ghr_abcdef1234567890",
                "token_type": "bearer",
                "expires_in": 3600,
            }

            code_verifier = "random_code_verifier_123456"

            # Save all OAuth data
            oauth_utils.save_client_info(server_url_hash, client_info, server_name)
            oauth_utils.save_tokens(server_url_hash, tokens, server_name)
            oauth_utils.save_code_verifier(server_url_hash, code_verifier, server_name)

            # Verify all data can be loaded correctly
            loaded_client = oauth_utils.load_client_info(server_url_hash, server_name)
            loaded_tokens = oauth_utils.load_tokens(server_url_hash, server_name)
            loaded_verifier = oauth_utils.load_code_verifier(server_url_hash, server_name)

            assert loaded_client == client_info
            assert loaded_tokens is not None, "Loaded tokens should not be None"
            assert loaded_tokens["access_token"] == tokens["access_token"]
            assert loaded_tokens["refresh_token"] == tokens["refresh_token"]
            assert loaded_verifier == code_verifier

            # Verify encryption was used for tokens
            tokens_path = oauth_utils.get_tokens_path(server_url_hash, server_name)
            with tokens_path.open() as f:
                file_content = json.load(f)
                assert file_content.get("encrypted") is True
                assert "gho_1234567890abcdef" not in json.dumps(file_content)

    def test_oauth_with_server_name_validation(self) -> None:
        """Test OAuth functions properly validate server names."""
        server_url_hash = "test123"

        # Valid server names should work
        valid_names = ["github-api", "slack_bot", "MyApp123"]
        for name in valid_names:
            try:
                oauth_utils.get_tokens_path(server_url_hash, name)
                # Should not raise exception
            except ValueError:
                pytest.fail(f"Valid server name '{name}' was rejected")

        # Invalid server names should be rejected (path traversal patterns only)
        invalid_names = ["../etc/passwd", "server/path", "server\\windows"]
        for name in invalid_names:
            with pytest.raises(ValueError, match="Server name"):
                oauth_utils.get_tokens_path(server_url_hash, name)

        # This name gets sanitized rather than rejected
        sanitized_path = oauth_utils.get_tokens_path(server_url_hash, "server<script>")
        assert "serverscript" in str(sanitized_path)

    def test_oauth_migration_from_legacy_format(self) -> None:
        """Test OAuth data migration from legacy format with security validation."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("mcp_foxxy_bridge.oauth.utils.get_oauth_config_dir") as mock_get_config,
        ):
            config_dir = Path(temp_dir)
            mock_get_config.return_value = config_dir

            server_url_hash = "legacy123"
            server_name = "migrated-server"

            # Create legacy token file
            legacy_tokens = {"access_token": "legacy_token_123", "refresh_token": "legacy_refresh_456"}

            legacy_path = config_dir / f"tokens-{server_url_hash}.json"
            with legacy_path.open("w") as f:
                json.dump(legacy_tokens, f)

            # Load tokens with server name (should trigger migration)
            with patch("mcp_foxxy_bridge.oauth.utils.ENCRYPTION_AVAILABLE", new=False):
                loaded_tokens = oauth_utils.load_tokens(server_url_hash, server_name)

            assert loaded_tokens is not None
            assert loaded_tokens["access_token"] == legacy_tokens["access_token"]

            # Verify legacy file was removed
            assert not legacy_path.exists()

            # Verify new file exists in correct location
            new_path = oauth_utils.get_tokens_path(server_url_hash, server_name)
            assert new_path.exists()


class TestSecurityBoundaries:
    """Test security boundaries and edge cases."""

    def test_mixed_environment_and_command_substitution(self) -> None:
        """Test mixed environment variables and command substitution."""
        test_cases = [
            ("${HOME}/$(whoami)", "Environment variable should work, command should be blocked"),
            ("$(echo ${HOME})", "Environment expansion within command should be handled safely"),
            ("${API_KEY:$(vault read secret)}", "Default command substitution should be blocked"),
        ]

        with patch.dict(os.environ, {"HOME": "/home/user"}, clear=True):
            for test_input, description in test_cases:
                # With command substitution disabled (default)
                result = expand_env_vars(test_input)
                # Environment variables should expand, commands should not
                assert "${HOME}" not in result or "$(whoami)" in result, f"Failed: {description}"

    def test_nested_security_bypass_attempts(self) -> None:
        """Test attempts to bypass security through nesting."""
        bypass_attempts = [
            "$(echo '$(rm -rf /)')",  # Nested command substitution
            "$(echo 'rm -rf /' | sh)",  # Command piping
            "${PATH:$(malicious_command)}",  # Command in default value
            "$(printf '%s' '${DANGEROUS_VAR}')",  # Environment var in command
        ]

        with patch.dict(os.environ, {"MCP_ALLOW_COMMAND_SUBSTITUTION": "true"}):
            for attempt in bypass_attempts:
                result = expand_env_vars(attempt)
                # These dangerous patterns should either be left unchanged (failed to execute)
                # or not contain the literal dangerous command
                # The key security test is that the dangerous commands are not actually executed
                if "$(rm -rf" in attempt:
                    # If the command contains rm -rf it should have failed to parse/execute and be left unchanged
                    assert result == attempt, f"Command was partially processed: {attempt} -> {result}"

    def test_file_permission_security(self) -> None:
        """Test that OAuth files have correct permissions."""
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("mcp_foxxy_bridge.oauth.utils.get_config_dir") as mock_get_config,
        ):
            config_dir = Path(temp_dir)
            mock_get_config.return_value = config_dir

            server_name = "test-server"
            server_url_hash = "test123"

            # Create test files
            test_data = {"test": "data"}
            oauth_utils.save_client_info(server_url_hash, test_data, server_name)
            oauth_utils.save_code_verifier(server_url_hash, "test_verifier", server_name)

            with patch("mcp_foxxy_bridge.oauth.utils.ENCRYPTION_AVAILABLE", new=False):
                oauth_utils.save_tokens(server_url_hash, test_data, server_name)

            # Check file permissions
            client_path = config_dir / "test_server" / "client.json"
            verifier_path = config_dir / "test_server" / "verifier.txt"
            tokens_path = config_dir / "test_server" / "tokens.json"

            for file_path in [client_path, verifier_path, tokens_path]:
                if file_path.exists():
                    # Check permissions are 600 (owner read/write only)
                    file_mode = oct(file_path.stat().st_mode)[-3:]
                    assert file_mode == "600", f"File {file_path} has incorrect permissions: {file_mode}"

    def test_configuration_with_all_security_features(self) -> None:
        """Test configuration loading with all security features enabled."""
        config_data = {
            "mcpServers": {
                "secure-server": {
                    "command": "python",
                    "args": ["-m", "secure_server"],
                    "env": {"API_KEY": "${API_SECRET}", "USER": "$(whoami)", "TIMESTAMP": "$(date +%s)"},
                    "oauth_config": {
                        "enabled": True,
                        "type": "proxy",
                        "client_id": "${OAUTH_CLIENT_ID}",
                        "authorization_url": "https://api.example.com/oauth/authorize",
                    },
                }
            },
            "bridge": {"host": "127.0.0.1", "port": 8080, "oauth_port": 8090},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f, indent=2)
            config_file = f.name

        try:
            env_vars = {
                "API_SECRET": "secret_api_key_123",
                "OAUTH_CLIENT_ID": "oauth_client_456",
                "MCP_ALLOW_COMMAND_SUBSTITUTION": "true",
            }

            with patch.dict(os.environ, env_vars):
                config = load_bridge_config_from_file(config_file, {})

                server = config.servers["secure-server"]

                # Environment variables should be expanded
                assert server.env is not None, "Server env should not be None"
                assert server.env["API_KEY"] == "secret_api_key_123"
                assert server.oauth_config is not None, "OAuth config should not be None"
                assert server.oauth_config["client_id"] == "oauth_client_456"

                # Safe command substitution should work
                assert server.env["USER"] != "$(whoami)"
                assert server.env["TIMESTAMP"] != "$(date +%s)"

                # OAuth should be configured
                assert server.is_oauth_enabled()
                assert server.needs_oauth_proxy()

                # Bridge configuration should be secure
                assert config.bridge is not None, "Bridge config should not be None"
                assert config.bridge.host == "127.0.0.1"  # Localhost only
                assert config.bridge.port == 8080
                assert config.bridge.oauth_port == 8090
        finally:
            Path(config_file).unlink()
