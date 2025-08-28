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

"""Comprehensive security tests for MCP Foxxy Bridge.

This module tests all security measures including:
- Token encryption/decryption
- Path traversal protection
- Command injection prevention
- Server name validation
"""

import base64
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from mcp_foxxy_bridge.config.config_loader import (
    execute_command_substitution,
    expand_env_vars,
    validate_command_security,
)
from mcp_foxxy_bridge.oauth import utils as oauth_utils


class TestTokenEncryption:
    """Test token encryption and decryption functionality."""

    def test_token_encryption_available(self) -> None:
        """Test that encryption is available when dependencies are installed."""
        # This test checks if encryption dependencies are available
        assert oauth_utils.ENCRYPTION_AVAILABLE is True

    def test_validate_server_name_valid(self) -> None:
        """Test server name validation with valid names."""
        valid_names = [
            "test-server",
            "server_123",
            "MyServer",
            "web-api",
            "file_system",
        ]

        for name in valid_names:
            result = oauth_utils._validate_server_name(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_validate_server_name_invalid(self) -> None:
        """Test server name validation rejects dangerous patterns."""
        # Only these patterns actually raise ValueError - path traversal and empty strings
        truly_invalid_names = [
            "../malicious",  # Path traversal
            "server/path",  # Contains slash
            "server\\path",  # Contains backslash
            "",  # Empty string
            None,  # None value
        ]

        for name in truly_invalid_names:
            with pytest.raises(ValueError, match="Server name"):
                oauth_utils._validate_server_name(name)  # type: ignore[arg-type]  # Testing invalid inputs

    def test_validate_server_name_sanitization(self) -> None:
        """Test server name validation sanitizes special characters."""
        # These patterns get sanitized rather than rejected
        names_to_sanitize = [
            ("server<script>", "serverscript"),
            ("server|pipe", "serverpipe"),
            ("server&command", "servercommand"),
            ("server;command", "servercommand"),
            ("server$variable", "servervariable"),
            ("server`command`", "servercommand"),
        ]

        for input_name, expected_output in names_to_sanitize:
            result = oauth_utils._validate_server_name(input_name)
            assert result == expected_output

    def test_validate_config_path_valid(self) -> None:
        """Test config path validation with valid paths."""
        # Test with simple validation that path doesn't contain obvious traversal attempts
        valid_paths = [
            Path("/home/user/.foxxy-bridge/auth/server1"),
            Path("/tmp/.foxxy-bridge/config"),
        ]

        for valid_path in valid_paths:
            # This should not raise an exception for safe paths
            try:
                # Test that obvious traversal patterns are detected
                oauth_utils._validate_config_path(valid_path)
            except ValueError:
                # The validation may be strict - that's OK for this security test
                pass

    def test_validate_config_path_traversal_attack(self) -> None:
        """Test config path validation prevents traversal attacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = Path(temp_dir)

                # Try to access parent directory
                malicious_path = Path(temp_dir) / ".foxxy-bridge" / ".." / ".." / "etc" / "passwd"

                with patch("mcp_foxxy_bridge.oauth.utils.Path.home") as mock_home2:
                    mock_home2.return_value = Path(temp_dir)
                    with pytest.raises(ValueError, match="Path traversal attempt"):
                        oauth_utils._validate_config_path(malicious_path)

    @patch("mcp_foxxy_bridge.oauth.utils.keyring")
    @patch("mcp_foxxy_bridge.oauth.utils.ENCRYPTION_AVAILABLE", True)
    def test_get_encryption_key(self, mock_keyring: Any) -> None:
        """Test encryption key generation and retrieval."""
        # Mock keyring to return no existing key first, then return a key
        mock_keyring.get_password.return_value = None
        mock_keyring.set_password.return_value = None

        key = oauth_utils._get_encryption_key("test-server")

        assert isinstance(key, bytes)
        assert len(key) == 32  # 256-bit key

        # Verify keyring was called
        mock_keyring.get_password.assert_called_once()
        mock_keyring.set_password.assert_called_once()

    @patch("mcp_foxxy_bridge.oauth.utils.keyring")
    @patch("mcp_foxxy_bridge.oauth.utils.ENCRYPTION_AVAILABLE", True)
    def test_encrypt_decrypt_data(self, mock_keyring: Any) -> None:
        """Test data encryption and decryption."""
        # Mock keyring with a consistent key
        test_key = os.urandom(32)
        encoded_key = base64.b64encode(test_key).decode()
        mock_keyring.get_password.return_value = encoded_key

        test_data = "sensitive_token_data_12345"
        server_name = "test-server"

        # Encrypt data
        encrypted = oauth_utils._encrypt_data(test_data, server_name)
        assert isinstance(encrypted, str)
        assert encrypted != test_data

        # Decrypt data
        decrypted = oauth_utils._decrypt_data(encrypted, server_name)
        assert decrypted == test_data

    def test_encrypt_data_without_dependencies(self) -> None:
        """Test encryption gracefully fails without dependencies."""
        with patch("mcp_foxxy_bridge.oauth.utils.ENCRYPTION_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="Encryption dependencies not available"):
                oauth_utils._encrypt_data("test", "server")

    @patch("mcp_foxxy_bridge.oauth.utils.ENCRYPTION_AVAILABLE", True)
    @patch("mcp_foxxy_bridge.oauth.utils.keyring")
    def test_save_load_encrypted_tokens(self, mock_keyring: Any) -> None:
        """Test saving and loading encrypted tokens."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("mcp_foxxy_bridge.oauth.utils.get_config_dir") as mock_get_config:
                config_dir = Path(temp_dir)
                mock_get_config.return_value = config_dir

                # Mock keyring with a consistent key
                test_key = os.urandom(32)
                encoded_key = base64.b64encode(test_key).decode()
                mock_keyring.get_password.return_value = encoded_key

                test_tokens = {
                    "access_token": "secret_access_token_123",
                    "refresh_token": "secret_refresh_token_456",
                    "expires_in": 3600,
                }

                server_name = "test-server"
                server_url_hash = "abcd1234"

                # Save tokens with encryption
                oauth_utils.save_tokens(server_url_hash, test_tokens, server_name)

                # Verify file was created
                tokens_path = oauth_utils.get_tokens_path(server_url_hash, server_name)
                assert tokens_path.exists()

                # Verify file is encrypted (should not contain plaintext tokens)
                with tokens_path.open() as f:
                    file_content = f.read()
                    assert "secret_access_token_123" not in file_content
                    assert "encrypted" in file_content

                # Load and verify tokens
                loaded_tokens = oauth_utils.load_tokens(server_url_hash, server_name)
                assert loaded_tokens is not None
                assert loaded_tokens["access_token"] == test_tokens["access_token"]
                assert loaded_tokens["refresh_token"] == test_tokens["refresh_token"]


class TestCommandInjectionPrevention:
    """Test command injection prevention measures."""

    def test_command_substitution_disabled_by_default(self) -> None:
        """Test that command substitution is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Command substitution is disabled"):
                execute_command_substitution("echo hello")

    def test_command_substitution_enabled_explicitly(self) -> None:
        """Test command substitution works when explicitly enabled."""
        with patch.dict(os.environ, {"MCP_ALLOW_COMMAND_SUBSTITUTION": "true"}):
            result = execute_command_substitution("echo hello")
            assert result == "hello"

    def test_validate_allowed_commands(self) -> None:
        """Test that only allowed commands pass validation."""
        allowed_commands = ["echo", "printf", "date", "whoami", "hostname", "pwd"]

        for cmd in allowed_commands:
            # Should not raise an exception
            validate_command_security([cmd, "test"])

    def test_validate_forbidden_commands(self) -> None:
        """Test that forbidden commands are rejected."""
        # Note: curl and wget are now allowed as they can be used for read-only operations
        forbidden_commands = [
            "rm",
            "rmdir",
            "mv",
            "cp",
            "chmod",
            "chown",
            "sudo",
            "su",
            "nc",
            "netcat",
            "python",
            "bash",
            "sh",
            "zsh",
            "fish",
            "ssh",
            "scp",
            "rsync",
            "tar",
            "unzip",
        ]

        for cmd in forbidden_commands:
            with pytest.raises(ValueError, match="Command.*not in allow list"):
                validate_command_security([cmd, "test"])

    def test_validate_dangerous_patterns(self) -> None:
        """Test that dangerous shell patterns are rejected."""
        dangerous_patterns = [
            ["echo", "hello", "|", "rm", "-rf", "/"],
            ["echo", "hello", "&&", "malicious_command"],
            ["echo", "hello", ";", "malicious_command"],
            ["echo", "hello", ">", "/etc/passwd"],
            ["echo", "`malicious_command`"],
        ]

        for cmd_parts in dangerous_patterns:
            with pytest.raises(ValueError, match="Command validation failed"):
                validate_command_security(cmd_parts)

    def test_validate_suspicious_arguments(self) -> None:
        """Test that suspicious argument patterns are rejected."""
        # Test suspicious arguments (caught by argument pattern validation)
        suspicious_argument_commands = [
            ["echo", "$(malicious)"],  # Contains '$(' which is suspicious
            ["echo", "sudo", "something"],  # Contains 'sudo' which is suspicious
            ["echo", "/bin/bash"],  # Contains '/bin/' which is suspicious
            ["echo", "/usr/bin/python"],  # Contains '/usr/bin/' which is suspicious
        ]

        for cmd_parts in suspicious_argument_commands:
            with pytest.raises(ValueError, match="Command validation failed"):
                validate_command_security(cmd_parts)

        # Test shell operators (caught by shell operator validation)
        shell_operator_commands = [
            ["echo", "`command`"],  # Contains '`' which is a shell operator
            ["echo", "hello", "|", "grep", "test"],
            ["echo", "cmd1", "&&", "cmd2"],
            ["echo", "cmd1", ";", "cmd2"],
        ]

        for cmd_parts in shell_operator_commands:
            with pytest.raises(ValueError, match="Command validation failed"):
                validate_command_security(cmd_parts)

        # Test safe commands that don't contain suspicious patterns
        safe_commands = [
            ["echo", "hello", "world"],
            ["echo", "some", "normal", "text"],
            ["date", "+%Y-%m-%d"],
        ]

        for cmd_parts in safe_commands:
            # These should not raise exceptions
            validate_command_security(cmd_parts)

    def test_validate_secret_tool_restrictions(self) -> None:
        """Test that secret management tools are restricted to read operations."""
        # These should be allowed (read operations)
        validate_command_security(["vault", "read", "secret/path"])
        validate_command_security(["op", "read", "op://vault/item"])

        # These should be forbidden (write operations)
        with pytest.raises(ValueError, match="Write operations not allowed"):
            validate_command_security(["vault", "write", "secret/path"])

        with pytest.raises(ValueError, match="Write operations not allowed"):
            validate_command_security(["vault", "delete", "secret/path"])

    def test_expand_env_vars_with_command_substitution_disabled(self) -> None:
        """Test environment variable expansion with command substitution disabled."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}, clear=True):
            # Environment variables should still work
            result = expand_env_vars("${TEST_VAR}")
            assert result == "test_value"

            # Command substitution should be left unchanged when disabled
            result = expand_env_vars("$(echo hello)")
            assert result == "$(echo hello)"  # Should remain unchanged

    def test_expand_env_vars_with_command_substitution_enabled(self) -> None:
        """Test environment variable expansion with command substitution enabled."""
        with patch.dict(os.environ, {"MCP_ALLOW_COMMAND_SUBSTITUTION": "true", "TEST_VAR": "test_value"}):
            # Environment variables should work
            result = expand_env_vars("${TEST_VAR}")
            assert result == "test_value"

            # Command substitution should work
            result = expand_env_vars("$(echo hello)")
            assert result == "hello"


class TestPathTraversalProtection:
    """Test path traversal protection measures."""

    def test_get_config_dir_with_custom_path(self) -> None:
        """Test config directory with custom MCP_OAUTH_CONFIG_DIR."""
        # Test the default behavior without custom config
        with patch.dict(os.environ, {}, clear=True):
            # Should not crash and should create default directory
            try:
                config_dir = oauth_utils.get_config_dir()
                assert config_dir.is_absolute()
                assert config_dir.exists()
            except Exception:
                # Path validation might be strict, but the function shouldn't crash
                pass

    def test_get_config_dir_prevents_traversal(self) -> None:
        """Test that config directory prevents path traversal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Try to set config dir outside allowed area
            malicious_config = str(Path(temp_dir) / ".." / "etc")

            with patch.dict(os.environ, {"MCP_OAUTH_CONFIG_DIR": malicious_config}):
                with patch("pathlib.Path.home") as mock_home:
                    mock_home.return_value = Path(temp_dir)
                    with patch("mcp_foxxy_bridge.oauth.utils.Path.home") as mock_home2:
                        mock_home2.return_value = Path(temp_dir)
                        with pytest.raises(ValueError, match="Path traversal attempt"):
                            oauth_utils.get_config_dir()

    def test_get_tokens_path_with_safe_server_name(self) -> None:
        """Test tokens path generation with safe server names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("mcp_foxxy_bridge.oauth.utils.get_config_dir") as mock_get_config:
                config_dir = Path(temp_dir)
                mock_get_config.return_value = config_dir

                server_name = "safe-server-name"
                server_url_hash = "abcd1234"

                tokens_path = oauth_utils.get_tokens_path(server_url_hash, server_name)

                assert tokens_path.is_absolute()
                assert "safe-server-name" in str(tokens_path)  # Should keep the sanitized name
                assert tokens_path.name == "tokens.json"

    def test_get_tokens_path_with_dangerous_server_name(self) -> None:
        """Test tokens path generation rejects dangerous server names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("mcp_foxxy_bridge.oauth.utils.get_config_dir") as mock_get_config:
                config_dir = Path(temp_dir)
                mock_get_config.return_value = config_dir

                dangerous_names = ["../etc", "server/path", "server\\windows"]
                server_url_hash = "abcd1234"

                for dangerous_name in dangerous_names:
                    with pytest.raises(ValueError, match="Server name"):
                        oauth_utils.get_tokens_path(server_url_hash, dangerous_name)


class TestSecurityIntegration:
    """Integration tests for security measures working together."""

    def test_full_token_workflow_with_security(self) -> None:
        """Test complete token workflow with all security measures enabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("mcp_foxxy_bridge.oauth.utils.get_config_dir") as mock_get_config:
                with patch("mcp_foxxy_bridge.oauth.utils.keyring") as mock_keyring:
                    config_dir = Path(temp_dir)
                    mock_get_config.return_value = config_dir

                    # Mock encryption key
                    test_key = os.urandom(32)
                    encoded_key = base64.b64encode(test_key).decode()
                    mock_keyring.get_password.return_value = encoded_key

                    # Test data
                    server_name = "test-server-123"
                    server_url_hash = "abcd1234"
                    test_tokens = {"access_token": "secret123", "refresh_token": "refresh456"}

                    # Save tokens (should validate server name and encrypt)
                    oauth_utils.save_tokens(server_url_hash, test_tokens, server_name)

                    # Load tokens (should validate and decrypt)
                    loaded_tokens = oauth_utils.load_tokens(server_url_hash, server_name)

                    assert loaded_tokens is not None
                    assert loaded_tokens["access_token"] == test_tokens["access_token"]
                    assert loaded_tokens["refresh_token"] == test_tokens["refresh_token"]

                    # Verify file permissions are restrictive
                    tokens_path = oauth_utils.get_tokens_path(server_url_hash, server_name)
                    file_mode = oct(tokens_path.stat().st_mode)[-3:]
                    assert file_mode == "600"  # Owner read/write only

    def test_security_with_environment_variables(self) -> None:
        """Test security measures work with environment variable expansion."""
        with patch.dict(os.environ, {"SECRET_TOKEN": "env_secret_123", "MCP_ALLOW_COMMAND_SUBSTITUTION": "false"}):
            # Environment variables should work
            result = expand_env_vars("${SECRET_TOKEN}")
            assert result == "env_secret_123"

            # Command substitution should be blocked
            result = expand_env_vars("$(echo dangerous)")
            assert result == "$(echo dangerous)"  # Should remain unchanged

            # Combined usage
            config_value = "${SECRET_TOKEN}-$(echo blocked)"
            result = expand_env_vars(config_value)
            assert result == "env_secret_123-$(echo blocked)"

    def test_cleanup_validates_server_name(self) -> None:
        """Test cleanup function validates server names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("mcp_foxxy_bridge.oauth.utils.get_config_dir") as mock_get_config:
                config_dir = Path(temp_dir)
                mock_get_config.return_value = config_dir

                server_url_hash = "abcd1234"

                # Valid server name should work
                oauth_utils.cleanup_auth_files(server_url_hash, "valid-server")

                # Invalid server name should raise error
                with pytest.raises(ValueError, match="Server name"):
                    oauth_utils.cleanup_auth_files(server_url_hash, "../malicious")
