"""Unit tests for typed message payloads."""

import unittest

from pydantic import ValidationError

from pandora_shared.payloads import (
    BriefReadyPayload,
    ParseResultPayload,
    SchemaReadyPayload,
    SchemaRequestWorkPayload,
)


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

    def test_brief_ready_requires_no_extra_validation_for_empty(self) -> None:
        payload = BriefReadyPayload()
        self.assertEqual(payload.input_gaps, [])

    def test_schema_ready_accepts_specs(self) -> None:
        payload = SchemaReadyPayload(
            component_specs=[{"name": "Button", "type": "button"}],
        )
        self.assertEqual(len(payload.component_specs), 1)


class SchemaRequestWorkPayloadTests(unittest.TestCase):
    def test_accepts_brief_extras_and_null_component_list(self) -> None:
        p = SchemaRequestWorkPayload.model_validate(
            {
                "design_flavour": "x",
                "component_list": None,
                "color_tokens": {"primary": "#000"},
                "tone": "friendly",
            }
        )
        self.assertEqual(p.component_list, [])
        self.assertEqual(p.model_dump().get("color_tokens"), {"primary": "#000"})


if __name__ == "__main__":
    unittest.main()
