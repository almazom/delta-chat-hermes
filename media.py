"""Media handling for the Delta Chat Hermes adapter."""

import logging
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("hermes_plugins.deltachat.media")


def resolve_blob_path(filename: str, dc_config_dir: str) -> Optional[str]:
    """Resolve a DC file path to an accessible absolute path."""
    if not filename:
        return None
    if os.path.exists(filename):
        return filename
    blob_path = os.path.join(dc_config_dir, "blobs", os.path.basename(filename))
    if os.path.exists(blob_path):
        return blob_path
    logger.warning("Media file not found at %r or %r", filename, blob_path)
    return None


def copy_to_hermes_cache(src: str, kind: str) -> str:
    """Copy a DC blob file into the Hermes cache directory."""
    try:
        ext = os.path.splitext(src)[1] or ""
        data = open(src, "rb").read()
        if kind == "audio":
            from gateway.platforms.base import cache_audio_from_bytes
            dest = cache_audio_from_bytes(data, ext=ext or ".ogg")
        elif kind == "image":
            from gateway.platforms.base import cache_image_from_bytes
            dest = cache_image_from_bytes(data, ext=ext or ".jpg")
        else:
            return src
        logger.info("Copied %s blob to Hermes cache: %s -> %s", kind, src, dest)
        return dest
    except Exception as e:
        logger.warning("Could not copy %s to Hermes cache: %s", src, e, exc_info=True)
    return src


def container_workspace_to_host(container_path: str) -> Optional[str]:
    """Map a /workspace/<rel> container path to its host-side sandbox path.

    Returns None when the path is not under /workspace/ or when the resolved
    path escapes the sandbox (path traversal attempt).
    """
    p = str(container_path)
    if not p.startswith("/workspace/"):
        return None
    rel = p[len("/workspace/"):]
    try:
        from tools.environments.base import get_sandbox_dir
        sandbox_workspace = get_sandbox_dir() / "docker" / "default" / "workspace"
    except ImportError:
        from gateway.config import get_hermes_home
        sandbox_workspace = Path(get_hermes_home()) / "sandboxes" / "docker" / "default" / "workspace"

    sandbox = sandbox_workspace.resolve()
    target = (sandbox / rel).resolve()
    # Reject traversal that resolves outside the sandbox workspace.
    if target != sandbox and not str(target).startswith(str(sandbox) + os.sep):
        logger.warning("Path traversal rejected for container path: %s", container_path)
        return None
    return str(target)


def copy_container_file_to_cache(container_path: str) -> Optional[str]:
    """Copy a /workspace/ container file to the Hermes docs cache."""
    from gateway.config import get_hermes_home

    host_path_str = container_workspace_to_host(container_path)
    if host_path_str is None:
        return None
    host_path = Path(host_path_str)
    if not host_path.is_file():
        logger.warning("Container output file not found on host: %s", host_path)
        return None
    docs_dir = Path(get_hermes_home()) / "cache" / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / host_path.name
    shutil.copy2(str(host_path), str(dest))
    logger.info("Copied container output %s -> %s", host_path.name, dest)
    return str(dest)


def extract_media(content: str, base_extract) -> Tuple[List[Tuple[str, bool]], str]:
    """Extend base extract_media to also handle .xdc MEDIA tags."""
    media_files, remaining = base_extract(content)
    xdc_re = re.compile(
        r'[`"\']?MEDIA:\s*[`"\']?((?:~/|/)[\w./\- ]+\.xdc)[`"\']?',
        re.IGNORECASE,
    )
    for match in xdc_re.finditer(content):
        path = match.group(1).strip()
        if not any(p == path for p, _ in media_files):
            media_files.append((path, False))
        remaining = remaining.replace(match.group(0), "").strip()
    return media_files, remaining


def extract_local_files(content: str, base_extract) -> Tuple[List[str], str]:
    """Extend base extract_local_files to also pick up bare /workspace/*.xdc paths."""
    files, remaining = base_extract(content)
    xdc_re = re.compile(r'(?<![/:\w.])(/workspace/[\w./\-]+\.xdc)\b', re.IGNORECASE)
    for match in xdc_re.finditer(content):
        path = match.group(1)
        if path not in files:
            files.append(path)
            remaining = remaining.replace(match.group(0), "").strip()
    return files, remaining


def filter_media_delivery_paths(media_files, base_filter) -> List[Tuple[str, bool]]:
    """Remap /workspace/ container paths to host cache before validation."""
    remapped = []
    for media_path, is_voice in media_files or []:
        p = str(media_path)
        if p.startswith("/workspace/"):
            cached = copy_container_file_to_cache(p)
            if cached:
                remapped.append((cached, is_voice))
                continue
            logger.warning("Could not resolve container path for delivery: %s", p)
        remapped.append((media_path, is_voice))
    return base_filter(remapped)


def filter_local_delivery_paths(file_paths, base_filter) -> List[str]:
    """Remap /workspace/ container paths to host cache before validation."""
    remapped = []
    for file_path in file_paths or []:
        p = str(file_path)
        if p.startswith("/workspace/"):
            cached = copy_container_file_to_cache(p)
            if cached:
                remapped.append(cached)
                continue
            logger.warning("Could not resolve container path for delivery: %s", p)
        else:
            remapped.append(file_path)
    return base_filter(remapped)
