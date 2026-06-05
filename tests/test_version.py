"""Tests for version parsing."""

from adapter import _parse_version


class TestVersionParsing:
    """Test version parsing functionality."""

    def test_parse_simple_version(self):
        """Test parsing simple version string."""
        assert _parse_version("2.51.0") == (2, 51, 0)

    def test_parse_version_with_suffix(self):
        """Test parsing version with -dev suffix."""
        assert _parse_version("2.51.0-dev") == (2, 51, 0)
        assert _parse_version("2.51.0-rc1") == (2, 51, 0)

    def test_parse_partial_version(self):
        """Test parsing partial version strings."""
        assert _parse_version("2.51") == (2, 51, 0)
        assert _parse_version("2") == (2, 0, 0)

    def test_parse_invalid_version(self):
        """Test parsing invalid version strings."""
        assert _parse_version("invalid") == (0, 0, 0)
        assert _parse_version("") == (0, 0, 0)
        assert _parse_version(None) == (0, 0, 0)

    def test_version_comparison(self):
        """Test that version tuples compare correctly."""
        assert _parse_version("2.51.0") >= _parse_version("2.51.0")
        assert _parse_version("2.52.0") > _parse_version("2.51.0")
        assert _parse_version("2.50.0") < _parse_version("2.51.0")
        assert _parse_version("3.0.0") > _parse_version("2.51.0")
        assert _parse_version("1.0.0") < _parse_version("2.51.0")
