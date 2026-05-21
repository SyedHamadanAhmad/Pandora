"""Unit tests for Sandpack showcase bundle assembly."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "pandora_shared") not in sys.path:
    sys.path.insert(0, str(ROOT / "pandora_shared"))

from pandora_shared.showcase_bundle import (  # noqa: E402
    build_fallback_scene_tsx,
    build_module_manifest,
    build_showcase_bundle,
    validate_scene_tsx,
)


class ShowcaseBundleTests(unittest.TestCase):
    def test_build_bundle_includes_component_files(self) -> None:
        components = [
            {
                "name": "Button",
                "tsx_code": "export function Button({ label }: { label: string }) { return <button>{label}</button>; }",
                "css_code": ".pandora-button { color: #111; }",
                "variants": ["primary"],
                "props": {"label": "Go"},
            }
        ]
        scene = (
            "import { Button } from './Button';\n"
            "export default function Showcase() {\n"
            '  return <div className="hero"><Button label="Go" variant="primary" onClick={() => {}} /></div>;\n'
            "}"
        )
        bundle = build_showcase_bundle(
            design_tokens={"primary": "#2563eb"},
            components=components,
            scene_tsx=scene,
            scene_css=".hero { padding: 24px; }",
        )
        self.assertIn("/Button.tsx", bundle["files"])
        self.assertIn("/Showcase.tsx", bundle["files"])
        self.assertIn("/tokens.css", bundle["files"])
        self.assertIn("--primary", bundle["files"]["/tokens.css"])
        self.assertEqual(bundle["entry"], "/index.tsx")

    def test_validate_rejects_unknown_import(self) -> None:
        manifest = build_module_manifest([{"name": "Button", "variants": ["primary"]}])
        scene = (
            "import { Card } from './Card';\n"
            "export default function Showcase() { return <Card title=\"x\" />; }\n"
        )
        errors = validate_scene_tsx(scene, manifest)
        self.assertTrue(any("unknown" in e for e in errors))

    def test_fallback_scene_imports_manifest_modules(self) -> None:
        manifest = build_module_manifest(
            [
                {
                    "name": "Button",
                    "variants": ["primary"],
                    "props": {"label": "Save"},
                }
            ]
        )
        tsx = build_fallback_scene_tsx(manifest, ["Button"])
        self.assertIn("from './Button'", tsx)
        self.assertIn("export default function Showcase", tsx)


if __name__ == "__main__":
    unittest.main()
