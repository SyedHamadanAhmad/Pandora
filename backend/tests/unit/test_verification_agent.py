"""Unit tests for Phase 7.1 VerificationAgent."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from pandora_shared.events import MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_shared.payloads import VerificationCompletePayload  # noqa: E402
from pandora_workers.agents.verification import (  # noqa: E402
    VerificationAgent,
    _deterministic_issues,
    _fallback_pass,
    _merge_verification,
)


class VerificationDeterministicTests(unittest.TestCase):
    def test_missing_primary_token_is_p2(self) -> None:
        work = {
            "design_tokens": {"primary": "#2563eb"},
            "components": [
                {
                    "id": 1,
                    "status": "validated",
                    "css_preview": ".btn { color: red; }",
                    "tsx_preview": "",
                },
            ],
        }
        issues = _deterministic_issues(work)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["priority"], "P2")
        self.assertEqual(issues[0]["component_id"], 1)

    def test_fallback_pass_not_approved_without_token(self) -> None:
        work = {
            "design_tokens": {"primary": "#111"},
            "components": [
                {"id": 3, "status": "validated", "css_preview": ".x{}", "tsx_preview": ""},
            ],
        }
        merged = _fallback_pass(work)
        self.assertFalse(merged["approved"])
        self.assertEqual(len(merged["revisions"]), 1)


class VerificationMergeTests(unittest.TestCase):
    def test_blocking_issue_sets_revisions(self) -> None:
        work = {"components": [{"id": 1, "name": "Button", "status": "validated"}]}
        llm = {
            "issues": [
                {"priority": "P2", "component_id": 1, "message": "Fix contrast"},
            ],
            "approved": False,
        }
        merged = _merge_verification(llm, work=work)
        self.assertFalse(merged["approved"])
        self.assertEqual(len(merged["revisions"]), 1)

    def test_failed_component_gets_p3(self) -> None:
        work = {
            "components": [
                {"id": 2, "name": "Card", "status": "failed", "error_reason": "tsc"},
            ]
        }
        merged = _fallback_pass(work)
        self.assertTrue(merged["approved"])
        self.assertEqual(merged["issues"][0]["priority"], "P3")


class VerificationAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_verification_complete(self) -> None:
        agent = VerificationAgent()
        work = MessageEnvelope(
            event="pandora.verification.start",
            project_id=10,
            pipeline_id=uuid4(),
            payload={
                "design_tokens": {"primary": "#000"},
                "components": [
                    {
                        "id": 1,
                        "name": "Button",
                        "status": "validated",
                        "tsx_preview": "x",
                        "css_preview": "background: #000;",
                    },
                ],
            },
        )
        llm_out = {"issues": [], "approved": True}
        with patch(
            "pandora_workers.agents.verification.complete_json",
            new_callable=AsyncMock,
            return_value=llm_out,
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.VERIFICATION_COMPLETE)
        data = VerificationCompletePayload.model_validate(result.payload)
        self.assertTrue(data.approved)


if __name__ == "__main__":
    unittest.main()
