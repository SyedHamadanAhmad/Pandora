"""Unit tests for API schema serialization."""

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.auth import AuthResponse, RegisterRequest
from app.schemas.project import CreateProjectRequest, ProjectResponse
from app.schemas.thread import CreateThreadResponse, ThreadMessageResponse
from pandora_shared.enums import MessageRole, ProjectStatus


class SchemaSerializationTests(unittest.TestCase):
    def test_register_request_accepts_snake_case(self) -> None:
        req = RegisterRequest.model_validate(
            {"email": "user@example.com", "password": "secret123"}
        )
        self.assertEqual(req.email, "user@example.com")

    def test_auth_response_serializes_user_id_camel_case(self) -> None:
        payload = AuthResponse(user_id=42).model_dump(mode="json", by_alias=True)
        self.assertEqual(payload, {"userId": 42})

    def test_project_response_from_attributes(self) -> None:
        class FakeProject:
            id = 1
            name = "Marketing"
            status = ProjectStatus.pending
            created_at = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
            updated_at = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)

        payload = ProjectResponse.model_validate(FakeProject()).model_dump(
            mode="json", by_alias=True
        )
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["name"], "Marketing")
        self.assertEqual(payload["status"], "pending")
        self.assertIn("createdAt", payload)
        self.assertIn("updatedAt", payload)

    def test_create_thread_response_no_pipeline_id(self) -> None:
        payload = CreateThreadResponse(
            message_id=7,
            created_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        ).model_dump(mode="json", by_alias=True)
        self.assertEqual(set(payload.keys()), {"messageId", "createdAt"})

    def test_thread_message_response_pipeline_id_nullable(self) -> None:
        pipeline_id = uuid4()
        msg = ThreadMessageResponse(
            id=1,
            role=MessageRole.user,
            content="hello",
            input_image_urls=["http://minio/img.png"],
            input_urls=["https://example.com"],
            pipeline_id=pipeline_id,
            created_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        )
        payload = msg.model_dump(mode="json", by_alias=True)
        self.assertEqual(payload["pipelineId"], str(pipeline_id))
        self.assertEqual(payload["inputImageUrls"], ["http://minio/img.png"])

    def test_create_project_request_validation(self) -> None:
        with self.assertRaises(Exception):
            CreateProjectRequest.model_validate({"name": ""})


if __name__ == "__main__":
    unittest.main()
