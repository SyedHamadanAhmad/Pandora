"""Unit tests for component API contracts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from pandora_workers.component_api_contracts import (  # noqa: E402
    check_api_contract,
    infer_spec_type,
)
from pandora_workers.agents.component_gen import (  # noqa: E402
    _fallback_badge,
    _fallback_button,
    _fallback_card,
)


class ComponentApiContractTests(unittest.TestCase):
    def test_infer_badge(self) -> None:
        self.assertEqual(infer_spec_type({"name": "StatusBadge"}), "badge")

    def test_button_fallback_label_and_onclick(self) -> None:
        out = _fallback_button(
            "Button",
            spec={"name": "Button", "type": "button"},
            design_tokens={"primary": "#000"},
            global_config=None,
        )
        self.assertIn("label: string", out["tsx_code"])
        self.assertNotIn("label?:", out["tsx_code"])
        self.assertIn("onClick?: () => void", out["tsx_code"])
        self.assertIn("onClick={onClick}", out["tsx_code"])
        self.assertIn("{label}", out["tsx_code"])
        self.assertNotIn("children:", out["tsx_code"])
        self.assertIn("label", out["props"])

    def test_card_fallback_requires_title(self) -> None:
        out = _fallback_card(
            "Card",
            spec={"name": "Card", "type": "card"},
            design_tokens=None,
            global_config=None,
        )
        self.assertIn("title: string", out["tsx_code"])
        self.assertNotIn("title?:", out["tsx_code"])

    def test_badge_fallback_requires_text(self) -> None:
        out = _fallback_badge(
            "Badge",
            spec={"name": "Badge", "type": "badge"},
            design_tokens={"primary": "#000"},
            global_config=None,
        )
        self.assertIn("text: string", out["tsx_code"])
        self.assertIn("<span", out["tsx_code"])
        self.assertIn("text", out["props"])

    def test_check_rejects_children_button(self) -> None:
        tsx = """
        import type { ReactNode } from 'react';
        export type ButtonProps = { children: ReactNode };
        export function Button({ children }: ButtonProps) {
          return <button onClick={() => {}}>{children}</button>;
        }
        """
        errors = check_api_contract(tsx, "button")
        self.assertTrue(len(errors) >= 1)

    def test_check_accepts_label_button(self) -> None:
        tsx = """
        export type ButtonProps = { label: string; onClick?: () => void };
        export function Button({ label, onClick }: ButtonProps) {
          return <button type="button" onClick={onClick}>{label}</button>;
        }
        """
        errors = check_api_contract(tsx, "button")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
