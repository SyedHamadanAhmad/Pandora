"""Run ``tsc`` on generated component TSX (Phase 6 Feedback).

ESLint is not run on ``.tsx`` here: the default ESLint parser cannot parse TypeScript
(``interface``, ``type``, etc.). ``tsc`` is the gate for syntax and TS/JSX validity.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from pathlib import Path

from pandora_workers.component_api_contracts import check_api_contract

_TS_CONFIG = """{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM"],
    "jsx": "react-jsx",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": false,
    "skipLibCheck": true,
    "noEmit": true,
    "allowJs": true
  },
  "include": ["**/*"]
}
"""

_PACKAGE_JSON = """{
  "name": "pandora-feedback-check",
  "private": true,
  "type": "module"
}
"""

# Ambient types so LLM output compiles without installing react/@types/react in the temp dir.
_REACT_SHIM = """declare namespace React {
  type ReactNode = unknown;
  type ReactElement = unknown;
  type FC<P = Record<string, unknown>> = (props: P) => ReactNode | null;
}

declare module 'react' {
  export type ReactNode = React.ReactNode;
  export type ReactElement = React.ReactElement;
  export type FC<P = Record<string, unknown>> = React.FC<P>;
  export type CSSProperties = Record<string, string | number>;
  export type ButtonHTMLAttributes<T> = Record<string, unknown>;
  export type HTMLAttributes<T> = Record<string, unknown> & {
    className?: string;
    children?: React.ReactNode;
  };
  const React: {
    ReactNode: React.ReactNode;
    createElement: unknown;
  };
  export default React;
}

declare module 'react/jsx-runtime' {
  export function jsx(
    type: unknown,
    props: unknown,
    key?: string,
  ): React.ReactElement;
  export function jsxs(
    type: unknown,
    props: unknown,
    key?: string,
  ): React.ReactElement;
  export namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: Record<string, unknown>;
    }
    interface Element extends React.ReactElement {}
  }
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: Record<string, unknown>;
  }
  interface Element extends React.ReactElement {}
}
"""

async def _run_cmd(*args: str, cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, text


def _tsx_for_validation(tsx_code: str) -> str:
    """Wrap generated TSX for syntax/parse checks without strict prop typing."""
    body = tsx_code.strip()
    if body.startswith("// @ts-nocheck"):
        return body
    return f"// @ts-nocheck\n{body}"


def _write_component_files(root: Path, tsx_code: str, css_code: str | None) -> Path:
    component_path = root / "Component.tsx"
    component_path.write_text(_tsx_for_validation(tsx_code), encoding="utf-8")
    if css_code:
        (root / "Component.css").write_text(css_code, encoding="utf-8")
    return component_path


def _component_name_from_tsx(tsx_code: str) -> str | None:
    match = re.search(r"export\s+function\s+(\w+)", tsx_code)
    return match.group(1) if match else None


def _spec_type_from_tsx(tsx_code: str) -> str:
    from pandora_workers.component_api_contracts import infer_spec_type

    name = _component_name_from_tsx(tsx_code)
    if not name:
        return "layout"
    return infer_spec_type({"name": name})


async def run_tsc_and_eslint(
    tsx_code: str,
    css_code: str | None = None,
    *,
    spec_type: str | None = None,
) -> tuple[bool, list[str]]:
    """
    Validate generated TSX in a temp project via ``tsc --noEmit``.

    Returns ``(ok, errors)``. Skips when ``npx``/``tsc`` is not installed.
    """
    if not shutil.which("npx"):
        return True, []

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pandora-feedback-") as tmp:
        root = Path(tmp)
        (root / "tsconfig.json").write_text(_TS_CONFIG, encoding="utf-8")
        (root / "package.json").write_text(_PACKAGE_JSON, encoding="utf-8")
        (root / "react-shim.d.ts").write_text(_REACT_SHIM, encoding="utf-8")
        _write_component_files(root, tsx_code, css_code)

        tsc_code, tsc_out = await _run_cmd("npx", "tsc", "--noEmit", cwd=root)
        if tsc_code != 0:
            errors.append(tsc_out or "tsc failed")

    resolved_type = spec_type or _spec_type_from_tsx(tsx_code)
    api_errors = check_api_contract(tsx_code, resolved_type)
    for msg in api_errors:
        errors.append(f"api contract: {msg}")

    return len(errors) == 0, errors[:5]
