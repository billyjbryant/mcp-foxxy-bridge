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

"""Tests for path security utilities."""

import tempfile
from pathlib import Path

import pytest

from mcp_foxxy_bridge.utils.path_security import (
    PathTraversalError,
    safe_write_file,
    validate_config_dir,
    validate_config_path,
    validate_safe_path,
)


class TestPathTraversalValidation:
    """Test path traversal attack prevention."""

    def test_detect_directory_traversal_simple(self) -> None:
        """Test detection of simple directory traversal attacks."""
        with pytest.raises(PathTraversalError):
            validate_safe_path("../../../etc/passwd")

    def test_detect_directory_traversal_complex(self) -> None:
        """Test detection of complex directory traversal attacks."""
        with pytest.raises(PathTraversalError):
            validate_safe_path("/tmp/config/../../../etc/passwd")

    def test_detect_null_byte_injection(self) -> None:
        """Test detection of null byte injection attacks."""
        with pytest.raises(PathTraversalError):
            validate_safe_path("/tmp/config.json\x00../../../etc/passwd")

    def test_detect_suspicious_components(self) -> None:
        """Test detection of various suspicious path components."""
        suspicious_paths = [
            "config/../../../etc/passwd",
            "/tmp/config/$/sensitive",
            "config/file..txt",  # Double dot in filename
        ]

        for path in suspicious_paths:
            with pytest.raises(PathTraversalError):
                validate_safe_path(path)

    def test_path_length_limit(self) -> None:
        """Test path length validation."""
        long_path = "a" * 5000  # Exceed max_path_length
        with pytest.raises(ValueError, match="Path too long"):
            validate_safe_path(long_path, max_path_length=4096)

    def test_empty_path_rejection(self) -> None:
        """Test rejection of empty paths."""
        with pytest.raises(ValueError, match="Path cannot be empty"):
            validate_safe_path("")

    def test_valid_paths_accepted(self) -> None:
        """Test that valid paths are accepted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Valid absolute path
            valid_path = temp_path / "config.json"
            result = validate_safe_path(valid_path, allowed_base_dirs=[temp_dir])
            assert result.is_absolute()
            # Check that result is within the temp directory (handle symlink resolution on macOS)
            assert str(temp_path.resolve()) in str(result.resolve())

            # Valid relative path that resolves within allowed directory
            result = validate_safe_path("config.json", allowed_base_dirs=[Path.cwd()])
            assert result.is_absolute()


class TestConfigPathValidation:
    """Test configuration-specific path validation."""

    def test_config_file_validation_success(self) -> None:
        """Test successful config file validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_file = temp_path / "config.json"

            result = validate_config_path(config_file, temp_path)
            assert result.is_absolute()
            assert result.suffix == ".json"

    def test_config_file_wrong_extension(self) -> None:
        """Test rejection of config files with wrong extensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_file = temp_path / "config.txt"

            with pytest.raises(ValueError, match="File extension not allowed"):
                validate_config_path(config_file, temp_path)

    def test_config_file_outside_base_dir(self) -> None:
        """Test rejection of config files outside allowed directories when restricted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Try to access file outside the config directory
            outside_file = Path("/tmp/malicious_config.json")

            with pytest.raises(PathTraversalError):
                validate_config_path(outside_file, temp_path)

    def test_config_file_unrestricted_allows_absolute_paths(self) -> None:
        """Test that unrestricted validation allows absolute paths."""
        # This should work for user-provided config files
        config_file = Path("/tmp/user_config.json")
        result = validate_config_path(config_file)  # No config_base_dir restriction
        assert result.is_absolute()
        assert result.name == "user_config.json"

    def test_config_file_unrestricted_still_blocks_traversal(self) -> None:
        """Test that unrestricted validation still blocks traversal attacks."""
        with pytest.raises(PathTraversalError):
            validate_config_path("../../../etc/passwd.json")  # Still has traversal

    def test_config_dir_validation_success(self) -> None:
        """Test successful config directory validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate_config_dir(temp_dir)
            assert result.is_absolute()
            assert result.exists()

    def test_config_dir_traversal_attack(self) -> None:
        """Test config directory validation against traversal attacks."""
        with pytest.raises(PathTraversalError):
            validate_config_dir("../../../tmp")

    def test_config_dir_file_instead_of_dir(self) -> None:
        """Test rejection when config dir path points to existing file."""
        with tempfile.NamedTemporaryFile() as temp_file:
            with pytest.raises(ValueError, match="Path exists but is not a directory"):
                validate_config_dir(temp_file.name)


class TestSafeFileWriting:
    """Test safe file writing functionality."""

    def test_safe_write_file_success(self) -> None:
        """Test successful safe file writing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "test.json"
            content = '{"test": "data"}'

            safe_write_file(test_file, content, [temp_path])

            assert test_file.exists()
            assert test_file.read_text(encoding="utf-8") == content

            # Check restrictive permissions (owner read/write only)
            stat_info = test_file.stat()
            assert stat_info.st_mode & 0o777 == 0o600

    def test_safe_write_file_outside_allowed_dir(self) -> None:
        """Test rejection of file writing outside allowed directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Try to write outside allowed directory
            outside_file = Path("/tmp/malicious.json")

            with pytest.raises(PathTraversalError):
                safe_write_file(outside_file, "malicious content", [temp_path])

    def test_safe_write_creates_parent_dirs(self) -> None:
        """Test that safe_write_file creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            nested_file = temp_path / "nested" / "dir" / "test.json"
            content = '{"nested": true}'

            safe_write_file(nested_file, content, [temp_path])

            assert nested_file.exists()
            assert nested_file.read_text(encoding="utf-8") == content


class TestPathTraversalAttackVectors:
    """Test various path traversal attack vectors."""

    def test_common_attack_vectors(self) -> None:
        """Test protection against common path traversal attack vectors."""
        attack_vectors = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",  # Windows style
            "/var/log/../../etc/passwd",
            "config/../../etc/passwd",
            "config/../../../etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # URL encoded
            "config.json/../../../etc/passwd",
            "./../../etc/passwd",
            "config.json\x00../../../etc/passwd",  # Null byte injection
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for attack_path in attack_vectors:
                with pytest.raises((PathTraversalError, ValueError)):
                    validate_safe_path(attack_path, allowed_base_dirs=[temp_dir])

    def test_symlink_attack_prevention(self) -> None:
        """Test prevention of symlink-based attacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a symlink pointing outside the allowed directory
            symlink_path = temp_path / "malicious_link"
            target_path = Path("/etc/passwd")

            try:
                symlink_path.symlink_to(target_path)

                # Should reject the symlink that points outside allowed directory
                with pytest.raises(PathTraversalError):
                    validate_safe_path(symlink_path, allowed_base_dirs=[temp_dir])

            except OSError:
                # Skip this test if symlinks can't be created (e.g., on Windows without admin)
                pytest.skip("Cannot create symlinks in this environment")

    def test_case_sensitivity_attacks(self) -> None:
        """Test handling of case sensitivity in path validation."""
        # These should be treated the same regardless of case
        paths = [
            "Config.JSON",
            "config.json",
            "CONFIG.JSON",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            for path in paths:
                # Should accept all case variations of valid extensions
                result = validate_config_path(temp_path / path, temp_path)
                assert result.suffix.lower() == ".json"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_unicode_paths(self) -> None:
        """Test handling of Unicode characters in paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            unicode_path = temp_path / "测试配置.json"  # Chinese characters

            result = validate_config_path(unicode_path, temp_path)
            assert result.is_absolute()

    def test_long_filename(self) -> None:
        """Test handling of long filenames within limits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Long but reasonable filename
            long_name = "a" * 200 + ".json"
            long_path = temp_path / long_name

            result = validate_config_path(long_path, temp_path)
            assert result.name.endswith(".json")

    def test_spaces_in_paths(self) -> None:
        """Test handling of spaces in file paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            spaced_path = temp_path / "my config file.json"

            result = validate_config_path(spaced_path, temp_path)
            assert " " in result.name
            assert result.suffix == ".json"
