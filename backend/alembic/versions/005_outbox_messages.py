"""Transactional outbox for reliable RabbitMQ publishes (W-B02)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_outbox_messages"
down_revision: Union[str, None] = "004_pipeline_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OUTBOX_NOTIFY_CHANNEL = "pandora_outbox"


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("queue_name", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_messages_idempotency_key"),
    )
    op.create_index("ix_outbox_messages_project_id", "outbox_messages", ["project_id"])
    op.create_index("ix_outbox_messages_status", "outbox_messages", ["status"])

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION notify_outbox_pending() RETURNS trigger AS $$
        BEGIN
            IF NEW.status = 'pending' THEN
                PERFORM pg_notify('{OUTBOX_NOTIFY_CHANNEL}', NEW.id::text);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbox_messages_notify_insert
        AFTER INSERT ON outbox_messages
        FOR EACH ROW
        EXECUTE FUNCTION notify_outbox_pending();
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbox_messages_notify_update
        AFTER UPDATE OF status ON outbox_messages
        FOR EACH ROW
        WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'pending')
        EXECUTE FUNCTION notify_outbox_pending();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS outbox_messages_notify_update ON outbox_messages")
    op.execute("DROP TRIGGER IF EXISTS outbox_messages_notify_insert ON outbox_messages")
    op.execute("DROP FUNCTION IF EXISTS notify_outbox_pending()")
    op.drop_index("ix_outbox_messages_status", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_project_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")
