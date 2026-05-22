"""HTTP tests for storybook read routes (Phase 1a / 1c)."""

from __future__ import annotations

import unittest
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from app.database import async_session
from app.main import app
from app.models.component import Component
from app.models.design_brief import DesignBrief
from app.models.design_schema import DesignSchema
from app.models.project import Project
from pandora_shared.enums import ComponentStatus, ProjectStatus


class StorybookRouteTests(unittest.IsolatedAsyncioTestCase):
    async def _register_and_login(self, client: AsyncClient) -> int:
        email = f"storybook-{uuid4()}@example.com"
        password = "secret123"
        register = await client.post(
            "/api/auth/register",
            json={"email": email, "password": password},
        )
        self.assertEqual(register.status_code, 201)
        user_id = register.json()["userId"]
        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(login.status_code, 200)
        client.cookies.update(login.cookies)
        return user_id

    async def _seed_project_library(self, user_id: int) -> tuple[int, int]:
        async with async_session() as db:
            project = Project(
                user_id=user_id,
                name="Storybook test",
                status=ProjectStatus.completed,
            )
            db.add(project)
            await db.flush()

            brief = DesignBrief(
                project_id=project.id,
                color_tokens={"primary": "#f97316"},
            )
            db.add(brief)
            await db.flush()

            schema = DesignSchema(
                project_id=project.id,
                brief_id=brief.id,
                design_tokens={"primary": "#f97316", "radius": "8px"},
                global_config={"theme": "light"},
                component_specs=[
                    {
                        "name": "Button",
                        "type": "button",
                        "variants": ["primary", "secondary"],
                    }
                ],
                component_count=1,
            )
            db.add(schema)
            await db.flush()

            component = Component(
                project_id=project.id,
                schema_id=schema.id,
                spec_index=0,
                name="Button",
                status=ComponentStatus.validated,
                tsx_code="export function Button() { return <button>OK</button>; }",
                css_code=".btn { color: var(--on-primary); }",
                variants=[{"name": "primary"}],
                props={"label": "Go"},
            )
            db.add(component)
            await db.commit()
            await db.refresh(component)
            return project.id, component.id

    async def test_storybook_overview_and_component_detail(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            user_id = await self._register_and_login(client)
            project_id, component_id = await self._seed_project_library(user_id)

            overview = await client.get(f"/api/projects/{project_id}/storybook")
            self.assertEqual(overview.status_code, 200)
            body = overview.json()
            self.assertEqual(body["projectId"], project_id)
            self.assertEqual(body["projectStatus"], "completed")
            self.assertEqual(body["designTokens"]["primary"], "#f97316")
            self.assertEqual(body["designTokens"]["onPrimary"], "#ffffff")
            self.assertIn("primary", body["tokenSchema"]["editable"])
            self.assertEqual(len(body["tokenSchema"]["semanticPairs"]), 4)
            self.assertEqual(body["summary"]["validated"], 1)
            self.assertEqual(body["components"][0]["previewAvailable"], True)
            self.assertIn("export function Button", body["components"][0]["tsxPreview"])

            detail = await client.get(
                f"/api/projects/{project_id}/components/{component_id}"
            )
            self.assertEqual(detail.status_code, 200)
            detail_body = detail.json()
            self.assertEqual(detail_body["component"]["name"], "Button")
            self.assertEqual(detail_body["spec"]["type"], "button")
            self.assertEqual(detail_body["designTokens"]["onPrimary"], "#ffffff")

            missing = await client.get(f"/api/projects/{project_id}/components/999999")
            self.assertEqual(missing.status_code, 404)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as other:
            await self._register_and_login(other)
            forbidden = await other.get(f"/api/projects/{project_id}/storybook")
        self.assertEqual(forbidden.status_code, 403)

    async def test_storybook_unauthenticated(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/projects/1/storybook")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
