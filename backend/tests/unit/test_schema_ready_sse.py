"""Unit tests for schema_ready SSE payload enrichment."""

from __future__ import annotations

import unittest

from app.services.pipeline_consumer import _component_names_from_specs
from pandora_shared.sse_events import SCHEMA_READY


class SchemaReadySseTests(unittest.TestCase):
    def test_component_names_from_specs(self) -> None:
        specs = [
            {"name": "Button"},
            {"name": "Card"},
            {},
        ]
        self.assertEqual(
            _component_names_from_specs(specs),
            ["Button", "Card", "component-2"],
        )

    def test_schema_ready_event_type_constant(self) -> None:
        self.assertEqual(SCHEMA_READY, "schema_ready")


if __name__ == "__main__":
    unittest.main()
