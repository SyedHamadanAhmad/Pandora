#!/usr/bin/env python3
"""Rebuild stored showcase_bundle JSON for scenes (e.g. after token/contrast fixes)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
for path in (ROOT, BACKEND):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.component import Component  # noqa: E402
from app.models.design_schema import DesignSchema  # noqa: E402
from app.models.showcase_scene import ShowcaseScene  # noqa: E402
from pandora_shared.enums import ComponentStatus  # noqa: E402
from pandora_shared.showcase_bundle import (  # noqa: E402
    build_showcase_bundle,
    components_for_bundle_from_db,
)


async def rebuild(project_id: int, *, dry_run: bool) -> None:
    async with async_session() as session:
        schema_row = await session.execute(
            select(DesignSchema)
            .where(DesignSchema.project_id == project_id)
            .order_by(DesignSchema.id.desc())
            .limit(1)
        )
        schema = schema_row.scalar_one_or_none()
        design_tokens = schema.design_tokens if schema and schema.design_tokens else {}

        comp_rows = await session.execute(
            select(Component)
            .where(
                Component.project_id == project_id,
                Component.status == ComponentStatus.validated,
            )
            .order_by(Component.spec_index.asc())
        )
        bundle_components = components_for_bundle_from_db(comp_rows.scalars().all())

        scene_rows = await session.execute(
            select(ShowcaseScene)
            .where(ShowcaseScene.project_id == project_id)
            .order_by(ShowcaseScene.scene_index.asc())
        )
        scenes = scene_rows.scalars().all()
        if not scenes:
            print(f"No showcase scenes for project {project_id}")
            return

        for scene in scenes:
            tsx = scene.scene_tsx_code or ""
            bundle = build_showcase_bundle(
                design_tokens=design_tokens,
                components=bundle_components,
                scene_tsx=tsx,
                scene_css=scene.scene_css_code,
                scene_index=scene.scene_index,
            )
            print(
                f"scene {scene.scene_index} ({scene.scene_name}): "
                f"{len(bundle.get('files') or {})} files"
            )
            if not dry_run:
                scene.showcase_bundle = bundle

        if not dry_run:
            await session.commit()
            print(f"Updated {len(scenes)} scene(s) for project {project_id}")
        else:
            print("dry-run: no DB writes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(rebuild(args.project_id, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
