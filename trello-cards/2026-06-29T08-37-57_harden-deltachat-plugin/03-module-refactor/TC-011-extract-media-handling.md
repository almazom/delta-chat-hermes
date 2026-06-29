# TC-011: Extract media handling to media.py

**Epic:** 03 — Module Refactor
**Story Points:** 3
**Priority:** P1
**Status:** TODO
**Dependencies:** None

## User Story

As a maintainer, I want blob resolution, Hermes cache copying, and container path remapping in one module, so that media handling is not scattered through `adapter.py`.

## Story Points:** 3

## Description

Move `_resolve_blob_path`, `_copy_to_hermes_cache`, `_container_workspace_to_host`, `_copy_container_file_to_cache`, and the `extract_media` / `filter_media_delivery_paths` overrides into `media.py`.

## Prerequisites

- None

## Implementation Steps

### Step 1: Create `media.py`

**File:** `media.py`

```python
import logging
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("hermes_plugins.deltachat.media")


def resolve_blob_path(filename: str, dc_config_dir: str) -> Optional[str]:
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
    return str(sandbox_workspace / rel)


def copy_container_file_to_cache(container_path: str) -> Optional[str]:
    import shutil
    from pathlib import Path
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


def extract_media(content: str, base_extract):
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


def extract_local_files(content: str, base_extract):
    files, remaining = base_extract(content)
    xdc_re = re.compile(r'(?<![/:\w.])(/workspace/[\w./\-]+\.xdc)\b', re.IGNORECASE)
    for match in xdc_re.finditer(content):
        path = match.group(1)
        if path not in files:
            files.append(path)
            remaining = remaining.replace(match.group(0), "").strip()
    return files, remaining


def filter_media_delivery_paths(media_files, base_filter):
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


def filter_local_delivery_paths(file_paths, base_filter):
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
```

### Step 2: Update `adapter.py` to import and delegate

**File:** `adapter.py`

```python
from media import (
    resolve_blob_path,
    copy_to_hermes_cache,
    extract_media as _extract_media,
    extract_local_files as _extract_local_files,
    filter_media_delivery_paths as _filter_media_delivery_paths,
    filter_local_delivery_paths as _filter_local_delivery_paths,
)
```

Replace methods with delegations:
```python
def _resolve_blob_path(self, filename: str) -> Optional[str]:
    return resolve_blob_path(filename, self._get_dc_config_dir())

def _copy_to_hermes_cache(self, src: str, kind: str) -> str:
    return copy_to_hermes_cache(src, kind)

def extract_media(self, content: str):
    from gateway.platforms.base import BasePlatformAdapter
    return _extract_media(content, BasePlatformAdapter.extract_media)

def extract_local_files(self, content: str):
    from gateway.platforms.base import BasePlatformAdapter
    return _extract_local_files(content, BasePlatformAdapter.extract_local_files)

def filter_media_delivery_paths(self, media_files):
    from gateway.platforms.base import BasePlatformAdapter
    return _filter_media_delivery_paths(media_files, BasePlatformAdapter.filter_media_delivery_paths)

def filter_local_delivery_paths(self, file_paths):
    from gateway.platforms.base import BasePlatformAdapter
    return _filter_local_delivery_paths(file_paths, BasePlatformAdapter.filter_local_delivery_paths)
```

### Step 3: Remove old implementations from `adapter.py`

**File:** `adapter.py:1096-1137`, `adapter.py:1140-1157` (wait, check exact lines)

Delete `_resolve_blob_path`, `_copy_to_hermes_cache`, and the media override methods' bodies (keep thin wrappers or remove entirely if base can call module functions).

### Step 4: Verify

```bash
python3 -m py_compile adapter.py media.py
```

**Expected:** No syntax errors.

## Acceptance Criteria

- [ ] `media.py` exists and exports media helpers.
- [ ] `adapter.py` delegates to `media.py`.
- [ ] Container path mapping behavior is preserved.

## Definition of Done

- Media handling is isolated in `media.py`.

## Dependencies
None

## What this is NOT
- It does not move the actual message-type dispatch logic.
- It does not change how files are sent to Delta Chat.

## Workflow lane evidence
- Review: inspect `media.py` and the delegations in `adapter.py`.
- Acceptance: `python3 -m py_compile adapter.py media.py` passes.
- Commit: `git add -A && git commit -m "TC-011: extract media handling to media.py"`
