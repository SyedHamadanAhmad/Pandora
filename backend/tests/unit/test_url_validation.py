"""Unit tests for safe URL validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SHARED = Path(__file__).resolve().parents[3] / "pandora_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from pandora_shared.url_validation import assert_safe_http_url  # noqa: E402


class UrlValidationTests(unittest.TestCase):
    def test_allows_public_https(self) -> None:
        assert_safe_http_url("https://example.com/page")

    def test_blocks_localhost(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_http_url("http://localhost/admin")

    def test_blocks_loopback_ip(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_http_url("http://127.0.0.1/")

    def test_blocks_metadata_ip(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_http_url("http://169.254.169.254/latest/meta-data")

    def test_blocks_non_http_scheme(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_http_url("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
