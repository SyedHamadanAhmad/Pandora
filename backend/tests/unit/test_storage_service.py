"""Tests for storage_service."""

import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from fastapi import UploadFile

from app.config import settings

from app.services.storage_service import (
    StorageValidationError,
    build_object_key,
    build_object_url,
    sanitize_filename,
    upload_thread_image,
    validate_image_bytes,
    validate_image_count,
)


class StorageHelpersTests(unittest.TestCase):
    def test_sanitize_filename_strips_paths(self) -> None:
        self.assertEqual(sanitize_filename("/tmp/evil/../ok.png"), "ok.png")

    def test_sanitize_filename_rejects_dotdot_name(self) -> None:
        with self.assertRaises(StorageValidationError):
            sanitize_filename("..")

    def test_build_object_key(self) -> None:
        key = build_object_key(1, 42, "shot.png")
        self.assertEqual(key, "1/messages/42/shot.png")

    def test_build_object_url(self) -> None:
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_endpoint = "http://minio:9000"
            mock_settings.minio_bucket = "pandora-images"
            url = build_object_url("1/messages/2/a.png")
        self.assertEqual(url, "http://minio:9000/pandora-images/1/messages/2/a.png")

    def test_validate_image_count(self) -> None:
        with self.assertRaises(StorageValidationError):
            validate_image_count([MagicMock()] * 6)

    def test_validate_image_bytes_rejects_large(self) -> None:
        with self.assertRaises(StorageValidationError):
            validate_image_bytes(b"x" * (10 * 1024 * 1024 + 1), "image/png", "a.png")

    def test_validate_image_bytes_rejects_mime(self) -> None:
        with self.assertRaises(StorageValidationError):
            validate_image_bytes(b"data", "application/pdf", "a.pdf")


class UploadThreadImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_calls_minio_and_returns_url(self) -> None:
        png_header = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        )
        upload = UploadFile(
            filename="tile.png",
            file=BytesIO(png_header),
            headers={"content-type": "image/png"},
        )

        with patch(
            "app.services.storage_service._put_object",
            return_value=None,
        ) as mock_put:
            url = await upload_thread_image(10, 20, upload)

        mock_put.assert_called_once()
        object_key, data, content_type = mock_put.call_args[0]
        self.assertEqual(object_key, "10/messages/20/tile.png")
        self.assertEqual(content_type, "image/png")
        self.assertIn("10/messages/20/tile.png", url)


class StorageServiceMinioIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_to_minio_when_available(self) -> None:
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        )
        upload = UploadFile(
            filename="integration.png",
            file=BytesIO(png_bytes),
            headers={"content-type": "image/png"},
        )

        from app.services.storage_service import _get_client

        try:
            client = _get_client()
            client.list_buckets()
        except Exception as exc:
            self.skipTest(f"MinIO not available: {exc}")

        object_key = f"99999/messages/1/integration-{id(self)}.png"
        with patch(
            "app.services.storage_service.build_object_key",
            return_value=object_key,
        ):
            url = await upload_thread_image(99999, 1, upload)

        self.assertIn(object_key, url)

        client = _get_client()
        stat = client.stat_object(settings.minio_bucket, object_key)
        self.assertGreater(stat.size, 0)
        client.remove_object(settings.minio_bucket, object_key)


if __name__ == "__main__":
    unittest.main()
