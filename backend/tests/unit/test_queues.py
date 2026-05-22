"""Unit tests for pandora_shared queue constants."""

import unittest

from pandora_shared.queues import (
    ALL_QUEUES,
    BRIEF_REQUEST,
    BRIEF_READY,
    SCHEMA_REQUEST,
    SCHEMA_READY,
)


class QueueConstantsTests(unittest.TestCase):
    def test_all_queues_includes_brief_schema_request_and_result(self) -> None:
        self.assertEqual(len(ALL_QUEUES), 16)
        self.assertIn(BRIEF_REQUEST, ALL_QUEUES)
        self.assertIn(BRIEF_READY, ALL_QUEUES)
        self.assertIn(SCHEMA_REQUEST, ALL_QUEUES)
        self.assertIn(SCHEMA_READY, ALL_QUEUES)

    def test_brief_schema_work_result_names(self) -> None:
        self.assertEqual(BRIEF_REQUEST, "pandora.brief.request")
        self.assertEqual(BRIEF_READY, "pandora.brief.ready")
        self.assertEqual(SCHEMA_REQUEST, "pandora.schema.request")
        self.assertEqual(SCHEMA_READY, "pandora.schema.ready")


if __name__ == "__main__":
    unittest.main()
