"""SQLAlchemy bindings for existing Postgres ENUM types."""

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import ENUM

from pandora_shared.enums import ComponentStatus, MessageRole, ProjectStatus

project_status_enum = ENUM(
    ProjectStatus,
    name="project_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

component_status_enum = ENUM(
    ComponentStatus,
    name="component_status",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

message_role_enum = ENUM(
    MessageRole,
    name="message_role",
    create_type=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

# Re-export for type hints in Mapped[] if needed
ProjectStatusEnum = Enum(ProjectStatus, name="project_status", create_constraint=False)
