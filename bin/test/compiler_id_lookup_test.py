"""Tests for compiler_id_lookup module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import lib.compiler_id_lookup as module
import pytest
import requests
from lib.compiler_id_lookup import (
    CompilerIdLookup,
    get_compiler_id_lookup,
    get_compiler_ids_for_exe,
    list_compiler_languages,
)


class TestListCompilerLanguages:
    """Tests for discovering the languages to load."""

    def test_lists_languages_of_amazon_properties_files(self):
        """Only Linux production configs count; other environments and directories are skipped."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "ada.amazon.properties", "type": "file"},
            {"name": "c++.amazon.properties", "type": "file"},
            {"name": "c++.amazonwin.properties", "type": "file"},
            {"name": "carbon.amazon.properties", "type": "file"},
            {"name": "carbon.defaults.properties", "type": "file"},
            {"name": "README.md", "type": "file"},
            {"name": "nested.amazon.properties", "type": "dir"},
        ]

        with patch("lib.compiler_id_lookup.requests.get", return_value=mock_response):
            assert list_compiler_languages() == ["ada", "c++", "carbon"]

    def test_raises_when_listing_fails(self):
        """A failed listing must not silently look like a CE with no compilers."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("403 rate limit exceeded")

        with patch("lib.compiler_id_lookup.requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError, match="rate limit"):
                list_compiler_languages()


class TestCompilerIdLookup:
    """Tests for the CompilerIdLookup class."""

    def test_get_compiler_ids_returns_empty_set_for_unknown_path(self):
        """Test that unknown exe paths return empty set."""
        with patch.object(CompilerIdLookup, "_load_all_properties"):
            lookup = CompilerIdLookup()
            lookup._loaded = True
            lookup._exe_to_ids = {}

            result = lookup.get_compiler_ids("/opt/compiler-explorer/unknown/bin/unknown")
            assert result == set()

    def test_get_compiler_ids_returns_matching_ids(self):
        """Test that known exe paths return their compiler IDs."""
        with patch.object(CompilerIdLookup, "_load_all_properties"):
            lookup = CompilerIdLookup()
            lookup._loaded = True
            lookup._exe_to_ids = {
                "/opt/compiler-explorer/gcc-14.2.0/bin/g++": {"g142", "objcppg142"},
                "/opt/compiler-explorer/clang-18.1.0/bin/clang++": {"clang1810"},
            }

            result = lookup.get_compiler_ids("/opt/compiler-explorer/gcc-14.2.0/bin/g++")
            assert result == {"g142", "objcppg142"}

    def test_get_all_mappings(self):
        """Test that get_all_mappings returns all mappings."""
        with patch.object(CompilerIdLookup, "_load_all_properties"):
            lookup = CompilerIdLookup()
            lookup._loaded = True
            lookup._exe_to_ids = {
                "/opt/compiler-explorer/gcc-14.2.0/bin/g++": {"g142"},
                "/opt/compiler-explorer/clang-18.1.0/bin/clang++": {"clang1810"},
            }

            result = lookup.get_all_mappings()
            assert len(result) == 2
            assert "/opt/compiler-explorer/gcc-14.2.0/bin/g++" in result

    def test_load_all_properties_covers_every_listed_language(self):
        """Exes are mapped for every language the listing returns, not a fixed subset."""
        properties = {
            "c++": {"g142": {"exe": "/opt/compiler-explorer/gcc-14.2.0/bin/g++"}, "noexe": {"name": "No exe"}},
            "carbon": {"carbon-x86-trunk": {"exe": "/opt/compiler-explorer/carbon-trunk/bin/carbon"}},
        }

        with (
            patch("lib.compiler_id_lookup.list_compiler_languages", return_value=list(properties)),
            patch.object(CompilerIdLookup, "_load_properties_for_language", side_effect=properties.get),
        ):
            lookup = CompilerIdLookup()

            assert lookup.get_compiler_ids("/opt/compiler-explorer/carbon-trunk/bin/carbon") == {"carbon-x86-trunk"}
            assert lookup.get_all_mappings() == {
                "/opt/compiler-explorer/gcc-14.2.0/bin/g++": {"g142"},
                "/opt/compiler-explorer/carbon-trunk/bin/carbon": {"carbon-x86-trunk"},
            }

    def test_load_properties_for_language_parses_correctly(self):
        """Test that properties file parsing works correctly."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = """
compiler.g142.exe=/opt/compiler-explorer/gcc-14.2.0/bin/g++
compiler.g142.semver=14.2
compiler.clang1810.exe=/opt/compiler-explorer/clang-18.1.0/bin/clang++
compiler.clang1810.semver=18.1.0
# This is a comment
group.gcc86.compilers=g142:g141
"""

        with patch("lib.compiler_id_lookup.requests.get", return_value=mock_response):
            lookup = CompilerIdLookup()
            compilers = lookup._load_properties_for_language("c++")

            assert "g142" in compilers
            assert compilers["g142"]["exe"] == "/opt/compiler-explorer/gcc-14.2.0/bin/g++"
            assert compilers["g142"]["semver"] == "14.2"
            assert "clang1810" in compilers
            assert compilers["clang1810"]["exe"] == "/opt/compiler-explorer/clang-18.1.0/bin/clang++"

    def test_load_properties_for_language_handles_fetch_failure(self):
        """Test that fetch failures are handled gracefully."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404

        with patch("lib.compiler_id_lookup.requests.get", return_value=mock_response):
            lookup = CompilerIdLookup()
            compilers = lookup._load_properties_for_language("nonexistent")

            assert compilers == {}

    def test_load_properties_for_language_handles_request_exception(self):
        """Test that request exceptions are handled gracefully."""
        with patch("lib.compiler_id_lookup.requests.get", side_effect=requests.RequestException("Network error")):
            lookup = CompilerIdLookup()
            compilers = lookup._load_properties_for_language("c++")

            assert compilers == {}


class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_get_compiler_id_lookup_returns_singleton(self):
        """Test that get_compiler_id_lookup returns the same instance."""
        module._lookup_instance = None

        with patch.object(CompilerIdLookup, "_load_all_properties"):
            lookup1 = get_compiler_id_lookup()
            lookup2 = get_compiler_id_lookup()

            assert lookup1 is lookup2

        # Clean up
        module._lookup_instance = None

    def test_get_compiler_ids_for_exe_uses_singleton(self):
        """Test that get_compiler_ids_for_exe uses the singleton instance."""
        module._lookup_instance = None

        with patch.object(CompilerIdLookup, "_load_all_properties"):
            with patch.object(CompilerIdLookup, "get_compiler_ids", return_value={"g142"}) as mock_get:
                result = get_compiler_ids_for_exe("/opt/compiler-explorer/gcc-14.2.0/bin/g++")

                assert result == {"g142"}
                mock_get.assert_called_once_with("/opt/compiler-explorer/gcc-14.2.0/bin/g++")

        # Clean up
        module._lookup_instance = None
