"""Unit tests for typed message payloads."""

import unittest

from pydantic import ValidationError

from pandora_shared.payloads import ParseResultPayload


class ParseResultPayloadTests(unittest.TestCase):
    def test_requires_source(self) -> None:
        with self.assertRaises(ValidationError):
            ParseResultPayload.model_validate({"data": {}})

    def test_rejects_invalid_source(self) -> None:
        with self.assertRaises(ValidationError):
            ParseResultPayload.model_validate({"source": "video"})

    def test_timeout_shape(self) -> None:
        payload = ParseResultPayload(source="text", data=None, error="timeout")
        self.assertEqual(payload.error, "timeout")
        self.assertIsNone(payload.data)


if __name__ == "__main__":
    unittest.main()
