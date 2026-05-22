"""Storybook HTTP tests live in tests/integration/test_storybook_api.py."""

from __future__ import annotations

import unittest


class StorybookRoutesMovedTests(unittest.TestCase):
    def test_integration_module_exists(self) -> None:
        import tests.integration.test_storybook_api as module

        self.assertTrue(hasattr(module, "test_storybook_overview_and_component_detail"))


if __name__ == "__main__":
    unittest.main()
