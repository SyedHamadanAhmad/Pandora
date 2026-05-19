"""Run ``tsc`` and ``eslint`` on generated component code (Phase 6 Feedback)."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

_TS_CONFIG = """{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM"],
    "jsx": "react-jsx",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
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


def _write_component_files(root: Path, tsx_code: str, css_code: str | None) -> Path:
    component_path = root / "Component.tsx"
    component_path.write_text(tsx_code, encoding="utf-8")
    if css_code:
        (root / "Component.css").write_text(css_code, encoding="utf-8")
    return component_path


async def run_tsc_and_eslint(
    tsx_code: str,
    css_code: str | None = None,
) -> tuple[bool, list[str]]:
    """
    Validate generated TSX in a temp project.

    Returns ``(ok, errors)``. Skips checks when ``tsc`` or ``eslint`` is not installed.
    """
    if not shutil.which("npx"):
        return True, []

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pandora-feedback-") as tmp:
        root = Path(tmp)
        (root / "tsconfig.json").write_text(_TS_CONFIG, encoding="utf-8")
        (root / "package.json").write_text(_PACKAGE_JSON, encoding="utf-8")
        _write_component_files(root, tsx_code, css_code)

        tsc_code, tsc_out = await _run_cmd("npx", "tsc", "--noEmit", cwd=root)
        if tsc_code != 0:
            errors.append(tsc_out or "tsc failed")

        eslint_bin = shutil.which("eslint")
        if eslint_bin:
            component = root / "Component.tsx"
            eslint_code, eslint_out = await _run_cmd(eslint_bin, str(component), cwd=root)
            if eslint_code != 0:
                errors.append(eslint_out or "eslint failed")

    return len(errors) == 0, errors[:5]
