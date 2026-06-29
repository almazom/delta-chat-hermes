"""Tests for media helper functions in media.py."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def dc_config_dir(tmp_path):
    """Create a fake Delta Chat config directory with a blobs subdir."""
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    return str(tmp_path)


class TestResolveBlobPath:
    def test_returns_absolute_path_when_file_exists(self, tmp_path):
        from media import resolve_blob_path

        f = tmp_path / "existing.txt"
        f.write_text("hi")
        assert resolve_blob_path(str(f), "/other") == str(f)

    def test_resolves_in_blobs_dir(self, dc_config_dir):
        from media import resolve_blob_path

        blob = Path(dc_config_dir) / "blobs" / "foo.bin"
        blob.write_bytes(b"data")
        assert resolve_blob_path("foo.bin", dc_config_dir) == str(blob)

    def test_returns_none_when_missing(self, dc_config_dir):
        from media import resolve_blob_path

        assert resolve_blob_path("missing.bin", dc_config_dir) is None

    def test_returns_none_for_empty_filename(self, dc_config_dir):
        from media import resolve_blob_path

        assert resolve_blob_path("", dc_config_dir) is None


class TestContainerWorkspaceToHost:
    def test_rejects_non_workspace_path(self):
        from media import container_workspace_to_host

        assert container_workspace_to_host("/tmp/file.txt") is None

    def test_maps_workspace_path(self, monkeypatch, tmp_path):
        from media import container_workspace_to_host

        workspace = tmp_path / "sandboxes" / "docker" / "default" / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "out.txt").write_text("ok")
        monkeypatch.setenv("HERMES_HOME_TEST", str(tmp_path))

        result = container_workspace_to_host("/workspace/out.txt")
        assert result == str(workspace / "out.txt")

    def test_rejects_path_traversal(self, monkeypatch, tmp_path):
        from media import container_workspace_to_host

        workspace = tmp_path / "sandboxes" / "docker" / "default" / "workspace"
        workspace.mkdir(parents=True)
        monkeypatch.setenv("HERMES_HOME_TEST", str(tmp_path))

        assert container_workspace_to_host("/workspace/../../etc/passwd") is None


class TestCopyContainerFileToCache:
    def test_copies_file_to_docs_cache(self, monkeypatch, tmp_path):
        from media import copy_container_file_to_cache

        workspace = tmp_path / "sandboxes" / "docker" / "default" / "workspace"
        workspace.mkdir(parents=True)
        src = workspace / "report.pdf"
        src.write_bytes(b"pdf")
        monkeypatch.setenv("HERMES_HOME_TEST", str(tmp_path))

        result = copy_container_file_to_cache("/workspace/report.pdf")
        assert result is not None
        assert result.endswith("report.pdf")
        assert Path(result).read_bytes() == b"pdf"

    def test_returns_none_when_file_missing(self, monkeypatch, tmp_path):
        from media import copy_container_file_to_cache

        workspace = tmp_path / "sandboxes" / "docker" / "default" / "workspace"
        workspace.mkdir(parents=True)
        monkeypatch.setenv("HERMES_HOME_TEST", str(tmp_path))

        assert copy_container_file_to_cache("/workspace/missing.txt") is None


class TestExtractMedia:
    def test_extracts_xdc_media_tag(self):
        from media import extract_media

        def base_extract(content):
            return [], content

        content = "Send MEDIA: /workspace/app.xdc and some text"
        media_files, remaining = extract_media(content, base_extract)
        assert media_files == [("/workspace/app.xdc", False)]
        assert "MEDIA:" not in remaining

    def test_does_not_duplicate_existing_paths(self):
        from media import extract_media

        def base_extract(content):
            return [("/workspace/app.xdc", False)], "some text"

        content = "Send MEDIA: /workspace/app.xdc"
        media_files, remaining = extract_media(content, base_extract)
        assert len(media_files) == 1


class TestExtractLocalFiles:
    def test_extracts_bare_workspace_xdc(self):
        from media import extract_local_files

        def base_extract(content):
            return [], content

        content = "Open /workspace/app.xdc please"
        files, remaining = extract_local_files(content, base_extract)
        assert files == ["/workspace/app.xdc"]


class TestFilterMediaDeliveryPaths:
    def test_remaps_workspace_path(self, monkeypatch, tmp_path):
        from media import filter_media_delivery_paths

        workspace = tmp_path / "sandboxes" / "docker" / "default" / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "img.jpg").write_text("img")
        monkeypatch.setenv("HERMES_HOME_TEST", str(tmp_path))

        def base_filter(paths):
            return paths

        result = filter_media_delivery_paths([("/workspace/img.jpg", False)], base_filter)
        assert len(result) == 1
        assert result[0][0].endswith("img.jpg")
        assert result[0][1] is False

    def test_keeps_non_workspace_paths(self):
        from media import filter_media_delivery_paths

        def base_filter(paths):
            return paths

        result = filter_media_delivery_paths([("/home/user/a.xdc", False)], base_filter)
        assert result == [("/home/user/a.xdc", False)]


class TestFilterLocalDeliveryPaths:
    def test_remaps_workspace_path(self, monkeypatch, tmp_path):
        from media import filter_local_delivery_paths

        workspace = tmp_path / "sandboxes" / "docker" / "default" / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "doc.txt").write_text("doc")
        monkeypatch.setenv("HERMES_HOME_TEST", str(tmp_path))

        def base_filter(paths):
            return paths

        result = filter_local_delivery_paths(["/workspace/doc.txt"], base_filter)
        assert len(result) == 1
        assert result[0].endswith("doc.txt")
