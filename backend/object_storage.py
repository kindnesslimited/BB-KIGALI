"""Emergent Object Storage helper — used to store admin-uploaded cover images."""
from __future__ import annotations

import logging
import os
import uuid
import mimetypes
from typing import Optional

import requests

logger = logging.getLogger(__name__)

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
APP_NAME = "bb-fm-kigali"

_storage_key: Optional[str] = None


def _init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    if not EMERGENT_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY missing — cannot use object storage")
    r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    r.raise_for_status()
    _storage_key = r.json()["storage_key"]
    logger.info("[storage] initialised object storage key")
    return _storage_key


def _put(path: str, data: bytes, content_type: str) -> dict:
    key = _init_storage()
    r = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    if r.status_code == 503:
        # Stale key — re-init once
        _init_storage(force=True)
        r = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": _init_storage(), "Content-Type": content_type},
            data=data,
            timeout=120,
        )
    r.raise_for_status()
    return r.json()


def _get(path: str) -> tuple[bytes, str]:
    key = _init_storage()
    r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if r.status_code == 503:
        _init_storage(force=True)
        r = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": _init_storage()}, timeout=60)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")


def guess_ext(filename: Optional[str], content_type: Optional[str]) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower()[:6]
    if content_type:
        ext = mimetypes.guess_extension(content_type) or ""
        return ext.lstrip(".").lower() or "bin"
    return "bin"


def upload_image_bytes(user_id: str, data: bytes, filename: Optional[str], content_type: Optional[str]) -> dict:
    """Upload a cover image and return { storagePath, contentType, size }.

    The public URL served through our backend is /api/uploads/{storagePath}.
    """
    ext = guess_ext(filename, content_type)
    if ext not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise ValueError("Only jpg/png/webp/gif images are accepted")
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Image is too large (max 8 MB)")
    if not content_type:
        content_type = mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
    obj_id = uuid.uuid4().hex
    path = f"{APP_NAME}/uploads/{user_id}/{obj_id}.{ext}"
    _put(path, data, content_type)
    return {"storagePath": path, "contentType": content_type, "size": len(data)}


def read_object(path: str) -> tuple[bytes, str]:
    return _get(path)
