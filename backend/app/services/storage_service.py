"""MinIO uploads for thread images (Tech Spec §10)."""

from __future__ import annotations

import asyncio
import io
import os
from functools import lru_cache
from urllib.parse import urlparse
from fastapi import UploadFile
from minio import Minio
from minio.commonconfig import CopySource

from app.config import settings

MAX_IMAGES_PER_REQUEST = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)


class StorageValidationError(ValueError):
    """Invalid image upload (type, size, count, or filename)."""


@lru_cache
def _get_client() -> Minio:
    parsed = urlparse(settings.minio_endpoint)
    if not parsed.hostname:
        raise RuntimeError(f"Invalid MINIO_ENDPOINT: {settings.minio_endpoint}")
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    secure = parsed.scheme == "https"
    return Minio(
        host,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def sanitize_filename(filename: str | None) -> str:
    """Use basename only; reject path traversal."""
    if not filename:
        raise StorageValidationError("Filename is required")
    base = os.path.basename(filename.strip())
    if not base or base in {".", ".."} or ".." in base:
        raise StorageValidationError("Invalid filename")
    return base


def build_object_key(project_id: int, message_id: int, filename: str) -> str:
    """Object key for Phase 2: {project_id}/messages/{message_id}/{filename}."""
    safe_name = sanitize_filename(filename)
    return f"{project_id}/messages/{message_id}/{safe_name}"


def build_pipeline_object_key(project_id: int, pipeline_run_id: int, filename: str) -> str:
    """Object key for pipeline images: {project_id}/runs/{pipeline_run_id}/{filename}."""
    safe_name = sanitize_filename(filename)
    return f"{project_id}/runs/{pipeline_run_id}/{safe_name}"


def object_key_from_url(url: str) -> str:
    """Extract object key from a URL stored in ``input_image_urls``."""
    prefix = f"{settings.minio_bucket}/"
    idx = url.find(prefix)
    if idx == -1:
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        if path.startswith(f"{settings.minio_bucket}/"):
            return path[len(settings.minio_bucket) + 1 :]
        raise StorageValidationError(f"Cannot parse MinIO object key from URL: {url}")
    return url[idx + len(prefix) :]


def build_object_url(object_key: str) -> str:
    """Public-style URL stored in ``thread_messages.input_image_urls``."""
    base = settings.minio_endpoint.rstrip("/")
    bucket = settings.minio_bucket
    return f"{base}/{bucket}/{object_key}"


def validate_image_count(files: list[UploadFile]) -> None:
    if len(files) > MAX_IMAGES_PER_REQUEST:
        raise StorageValidationError(
            f"At most {MAX_IMAGES_PER_REQUEST} images allowed per request"
        )


def validate_image_bytes(data: bytes, content_type: str | None, filename: str | None) -> None:
    if len(data) > MAX_IMAGE_BYTES:
        raise StorageValidationError(
            f"Image exceeds maximum size of {MAX_IMAGE_BYTES // (1024 * 1024)} MB"
        )
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise StorageValidationError(f"Unsupported image type: {mime or 'unknown'}")
    sanitize_filename(filename)


def _put_object(object_key: str, data: bytes, content_type: str) -> None:
    client = _get_client()
    client.put_object(
        settings.minio_bucket,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def _copy_object(source_key: str, dest_key: str) -> None:
    client = _get_client()
    client.copy_object(
        settings.minio_bucket,
        dest_key,
        CopySource(settings.minio_bucket, source_key),
    )


async def copy_thread_images_to_pipeline(
    project_id: int,
    pipeline_run_id: int,
    image_urls: list[str],
) -> list[str]:
    """Copy message-scoped images to the pipeline prefix and return new URLs."""
    copied_urls: list[str] = []
    for url in image_urls:
        source_key = object_key_from_url(url)
        filename = os.path.basename(source_key)
        dest_key = build_pipeline_object_key(project_id, pipeline_run_id, filename)
        await asyncio.to_thread(_copy_object, source_key, dest_key)
        copied_urls.append(build_object_url(dest_key))
    return copied_urls


async def upload_thread_image(
    project_id: int,
    message_id: int,
    file: UploadFile,
) -> str:
    """
    Upload one thread image to MinIO.

    Returns a URL string for ``thread_messages.input_image_urls``.
    """
    data = await file.read()
    content_type = (file.content_type or "application/octet-stream").split(";", 1)[0].strip()
    validate_image_bytes(data, content_type, file.filename)

    object_key = build_object_key(project_id, message_id, file.filename or "image")
    await asyncio.to_thread(_put_object, object_key, data, content_type)
    return build_object_url(object_key)
