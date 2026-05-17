"""Initial POC schema — Tech Spec v1.7 §4.

Revision ID: 001
Revises:
Create Date: 2026-05-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

project_status_enum = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    name="project_status",
    create_type=False,
)
component_status_enum = postgresql.ENUM(
    "generating",
    "validating",
    "validated",
    "failed",
    "revised",
    name="component_status",
    create_type=False,
)
message_role_enum = postgresql.ENUM(
    "user",
    "system",
    name="message_role",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    project_status_enum.create(bind, checkfirst=True)
    component_status_enum.create(bind, checkfirst=True)
    message_role_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            project_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "thread_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", message_role_enum, nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("input_image_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_thread_messages_project_id", "thread_messages", ["project_id"])

    op.create_table(
        "design_briefs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("color_tokens", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("typography_scale", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("spacing_system", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("design_flavour", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tone", sa.Text(), nullable=True),
        sa.Column("component_list", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", name="uq_design_briefs_project_id"),
    )

    op.create_table(
        "design_schemas",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("brief_id", sa.BigInteger(), nullable=False),
        sa.Column("design_tokens", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("global_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("component_specs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("component_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brief_id"], ["design_briefs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_design_schemas_project_id", "design_schemas", ["project_id"])

    op.create_table(
        "components",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("schema_id", sa.BigInteger(), nullable=False),
        sa.Column("spec_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("tsx_code", sa.Text(), nullable=True),
        sa.Column("css_code", sa.Text(), nullable=True),
        sa.Column(
            "status",
            component_status_enum,
            nullable=False,
            server_default="generating",
        ),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision_round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("props", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("variants", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("revision_instruction", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schema_id"], ["design_schemas.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_components_project_id", "components", ["project_id"])

    op.create_table(
        "showcase_scenes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("scene_name", sa.String(length=100), nullable=True),
        sa.Column("scene_tsx_code", sa.Text(), nullable=True),
        sa.Column("scene_css_code", sa.Text(), nullable=True),
        sa.Column("components_used", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_showcase_scenes_project_id", "showcase_scenes", ["project_id"])

    op.create_table(
        "processed_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_processed_events_idempotency_key"),
    )
    op.create_index("ix_processed_events_project_id", "processed_events", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_processed_events_project_id", table_name="processed_events", if_exists=True)
    op.drop_table("processed_events")
    op.drop_index("ix_showcase_scenes_project_id", table_name="showcase_scenes", if_exists=True)
    op.drop_table("showcase_scenes")
    op.drop_index("ix_components_project_id", table_name="components", if_exists=True)
    op.drop_table("components")
    op.drop_index("ix_design_schemas_project_id", table_name="design_schemas", if_exists=True)
    op.drop_table("design_schemas")
    op.drop_table("design_briefs")
    op.drop_index("ix_thread_messages_project_id", table_name="thread_messages", if_exists=True)
    op.drop_table("thread_messages")
    op.drop_index("ix_projects_user_id", table_name="projects", if_exists=True)
    op.drop_table("projects")
    op.drop_index("ix_sessions_user_id", table_name="sessions", if_exists=True)
    op.drop_table("sessions")
    op.drop_index("ix_users_email", table_name="users", if_exists=True)
    op.drop_table("users")

    bind = op.get_bind()
    message_role_enum.drop(bind, checkfirst=True)
    component_status_enum.drop(bind, checkfirst=True)
    project_status_enum.drop(bind, checkfirst=True)
