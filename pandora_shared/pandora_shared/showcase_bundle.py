"""Sandpack file-map assembly for showcase scenes (Track B hybrid)."""

from __future__ import annotations

import re
from typing import Any

from pandora_shared.design_color import enrich_semantic_color_tokens

SANDPACK_DEPENDENCIES: dict[str, str] = {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
}

_IMPORT_RE = re.compile(
    r"""import\s+(?:type\s+)?(?:\{[^}]+\}|\w+)\s+from\s+['"]\.\/([^'"]+)['"]""",
)
_EXPORT_SHOWCASE_RE = re.compile(
    r"export\s+default\s+function\s+Showcase|export\s+function\s+Showcase",
)


def _normalize_variants(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return ["default"]
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            name = item.strip()
            if name not in out:
                out.append(name)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("id")
            if isinstance(name, str) and name.strip() and name.strip() not in out:
                out.append(name.strip())
    return out or ["default"]


def build_module_manifest(components: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic import table for LLM scene composition."""
    modules: dict[str, Any] = {}
    for comp in components:
        if not isinstance(comp, dict):
            continue
        name = str(comp.get("name") or "").strip()
        if not name:
            continue
        props = comp.get("props")
        props_defaults = dict(props) if isinstance(props, dict) else {}
        comp_type = str(comp.get("type") or "").strip() or None
        modules[name] = {
            "path": f"/{name}.tsx",
            "export": name,
            "variants": _normalize_variants(comp.get("variants")),
            "props_defaults": props_defaults,
            "type": comp_type,
        }
    return {
        "modules": modules,
        "tokens_path": "/tokens.css",
        "styles_path": "/styles.css",
        "app_path": "/App.tsx",
        "entry_path": "/index.tsx",
    }


def flatten_design_tokens_to_css_vars(tokens: dict[str, Any]) -> str:
    """Emit :root variables from design_tokens (including nested typography/spacing)."""

    def walk(obj: dict[str, Any], prefix: str) -> list[str]:
        lines: list[str] = []
        for key, value in obj.items():
            var_key = f"{prefix}-{key}" if prefix else str(key)
            var_key = var_key.replace("_", "-")
            if isinstance(value, str) and value.strip():
                lines.append(f"  --{var_key}: {value.strip()};")
            elif isinstance(value, (int, float)):
                lines.append(f"  --{var_key}: {value};")
            elif isinstance(value, dict):
                lines.extend(walk(value, var_key))
        return lines

    if not tokens:
        return ":root {\n  --primary: #2563eb;\n  --on-primary: #ffffff;\n}\n"
    tokens = enrich_semantic_color_tokens(tokens)
    lines = walk(tokens, "")
    if not any("--primary" in line for line in lines):
        primary = tokens.get("primary")
        if isinstance(primary, str) and primary.strip():
            lines.insert(0, f"  --primary: {primary.strip()};")
    return ":root {\n" + "\n".join(lines) + "\n}\n"


def _aggregate_component_css(components: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        css = comp.get("css_code")
        if isinstance(css, str) and css.strip():
            name = comp.get("name") or "component"
            parts.append(f"/* --- {name} --- */\n{css.strip()}")
    return "\n\n".join(parts)


def extract_imported_module_names(scene_tsx: str) -> set[str]:
    names: set[str] = set()
    for match in _IMPORT_RE.finditer(scene_tsx):
        base = match.group(1).strip()
        if base.endswith(".tsx"):
            base = base[: -4]
        if base.endswith(".ts"):
            base = base[: -3]
        if base:
            names.add(base)
    return names


def validate_scene_tsx(scene_tsx: str, manifest: dict[str, Any]) -> list[str]:
    """Return validation errors; empty if scene only imports known modules."""
    errors: list[str] = []
    modules = manifest.get("modules") if isinstance(manifest.get("modules"), dict) else {}
    allowed = set(modules.keys())

    if not _EXPORT_SHOWCASE_RE.search(scene_tsx):
        errors.append("scene must export default function Showcase or export function Showcase")

    imported = extract_imported_module_names(scene_tsx)
    unknown = sorted(imported - allowed)
    if unknown:
        errors.append(f"unknown imports: {', '.join(unknown)}")
    return errors


def normalize_scene_entry(scene_tsx: str) -> str:
    """Ensure Sandpack entry exports Showcase."""
    body = scene_tsx.strip()
    if _EXPORT_SHOWCASE_RE.search(body):
        return body
    if body.startswith("(") or body.startswith("<"):
        return (
            "export default function Showcase() {\n"
            f"  return (\n    {body}\n  );\n"
            "}"
        )
    return f"export default function Showcase() {{\n  return (\n    <>{body}</>\n  );\n}}\n"


def _props_to_jsx_attrs(
    props: dict[str, Any],
    *,
    variant: str | None = None,
    component_type: str | None = None,
) -> str:
    attrs: list[str] = []
    if variant and variant != "default":
        attrs.append(f'variant="{variant}"')
    for key, value in props.items():
        if key in ("children", "onClick"):
            continue
        if value is None:
            continue
        if key == "onClick" or (isinstance(value, str) and value.startswith("()")):
            attrs.append("onClick={() => {}}")
        elif isinstance(value, str):
            escaped = value.replace('"', '\\"')
            attrs.append(f'{key}="{escaped}"')
        elif isinstance(value, bool):
            attrs.append(f"{key}={str(value).lower()}")
        elif isinstance(value, (int, float)):
            attrs.append(f"{key}={{{value}}}")
        elif isinstance(value, list):
            inner = ", ".join(repr(x) for x in value if isinstance(x, str))
            attrs.append(f"{key}={{{inner}}}")
    if component_type == "button" and "onClick" not in " ".join(attrs):
        attrs.append("onClick={() => {}}")
    return " ".join(attrs)


def build_fallback_scene_tsx(
    manifest: dict[str, Any],
    component_names: list[str] | None = None,
) -> str:
    """Minimal valid scene when LLM output fails lint."""
    modules = manifest.get("modules") if isinstance(manifest.get("modules"), dict) else {}
    names = component_names or list(modules.keys())
    names = [n for n in names if n in modules][:8]
    if not names:
        names = list(modules.keys())[:8]

    import_lines = [f"import {{ {name} }} from './{name}';" for name in names]
    render_lines: list[str] = []
    for name in names:
        mod = modules[name] if isinstance(modules.get(name), dict) else {}
        variants = mod.get("variants") if isinstance(mod.get("variants"), list) else ["default"]
        variant = variants[0] if variants else "default"
        props = mod.get("props_defaults") if isinstance(mod.get("props_defaults"), dict) else {}
        comp_type = mod.get("type") if isinstance(mod.get("type"), str) else None
        attrs = _props_to_jsx_attrs(props, variant=variant, component_type=comp_type)
        render_lines.append(f"      <{name} {attrs} />")

    imports = "\n".join(import_lines)
    body = "\n".join(render_lines) if render_lines else '      <p className="pandora-showcase-empty">No components</p>'
    return (
        f"{imports}\n\n"
        "export default function Showcase() {\n"
        "  return (\n"
        '    <div className="pandora-showcase-fallback">\n'
        f"{body}\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )


def _app_imports_showcase(scene_tsx: str) -> str:
    if "export default function Showcase" in scene_tsx:
        return (
            'import "./styles.css";\n'
            "import Showcase from \"./Showcase\";\n\n"
            "export default function App() {\n"
            "  return <Showcase />;\n"
            "}\n"
        )
    return (
        'import "./styles.css";\n'
        "import { Showcase } from \"./Showcase\";\n\n"
        "export default function App() {\n"
        "  return <Showcase />;\n"
        "}\n"
    )


def build_showcase_bundle(
    *,
    design_tokens: dict[str, Any] | None,
    components: list[dict[str, Any]],
    scene_tsx: str,
    scene_css: str | None = None,
    scene_index: int = 0,
) -> dict[str, Any]:
    """Build Sandpack-ready file map: library files + LLM scene entry."""
    tokens = design_tokens if isinstance(design_tokens, dict) else {}
    scene_entry = normalize_scene_entry(scene_tsx)
    showcase_path = "/Showcase.tsx"

    files: dict[str, str] = {
        "/tokens.css": flatten_design_tokens_to_css_vars(tokens),
        showcase_path: scene_entry,
        "/App.tsx": _app_imports_showcase(scene_entry),
        "/index.tsx": (
            'import { StrictMode } from "react";\n'
            'import { createRoot } from "react-dom/client";\n'
            "import App from \"./App\";\n\n"
            'createRoot(document.getElementById("root")!).render(\n'
            "  <StrictMode>\n"
            "    <App />\n"
            "  </StrictMode>,\n"
            ");\n"
        ),
    }

    for comp in components:
        if not isinstance(comp, dict):
            continue
        name = str(comp.get("name") or "").strip()
        tsx = comp.get("tsx_code")
        if not name or not isinstance(tsx, str) or not tsx.strip():
            continue
        files[f"/{name}.tsx"] = tsx.strip()

    scene_styles = scene_css.strip() if isinstance(scene_css, str) and scene_css.strip() else ""
    component_styles = _aggregate_component_css(components)
    files["/styles.css"] = (
        '@import "./tokens.css";\n\n'
        f"/* scene {scene_index} */\n{scene_styles}\n\n"
        f"{component_styles}\n"
    ).strip() + "\n"

    return {
        "files": files,
        "entry": "/index.tsx",
        "dependencies": dict(SANDPACK_DEPENDENCIES),
        "showcase_path": showcase_path,
    }


def components_for_bundle_from_db(
    rows: list[Any],
) -> list[dict[str, Any]]:
    """Map SQLAlchemy Component rows to bundle builder input."""
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "name": row.name,
                "tsx_code": row.tsx_code,
                "css_code": row.css_code,
                "variants": row.variants,
                "props": row.props,
            }
        )
    return out
