"""pipeline_runs table; thread_messages.pipeline_run_id replaces pipeline_id UUID."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_pipeline_runs"
down_revision: Union[str, None] = "003_drop_showcase_scenes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_message_id", sa.BigInteger(), nullable=False),
        sa.Column("url_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("parse_expected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("parse_received", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "parse_pending",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "parse_results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("expected_components", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolved_components", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision_round", sa.Integer(), server_default="0", nullable=False),
        sa.Column("run_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("brief_requested", sa.Boolean(), server_default="false", nullable=False),
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
        sa.ForeignKeyConstraint(["thread_message_id"], ["thread_messages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("thread_message_id", name="uq_pipeline_runs_thread_message_id"),
    )
    op.create_index("ix_pipeline_runs_project_id", "pipeline_runs", ["project_id"])

    op.add_column(
        "thread_messages",
        sa.Column("pipeline_run_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_thread_messages_pipeline_run_id",
        "thread_messages",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_thread_messages_pipeline_run_id",
        "thread_messages",
        ["pipeline_run_id"],
    )

    op.drop_column("thread_messages", "pipeline_id")


def downgrade() -> None:
    op.add_column(
        "thread_messages",
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.drop_index("ix_thread_messages_pipeline_run_id", table_name="thread_messages")
    op.drop_constraint(
        "fk_thread_messages_pipeline_run_id",
        "thread_messages",
        type_="foreignkey",
    )
    op.drop_column("thread_messages", "pipeline_run_id")
    op.drop_index("ix_pipeline_runs_project_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
