"""Drop showcase_scenes table (showcase phased out; storybook is primary UX)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_drop_showcase_scenes"
down_revision: Union[str, None] = "002_showcase_bundle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_showcase_scenes_project_id", table_name="showcase_scenes", if_exists=True)
    op.drop_table("showcase_scenes")


def downgrade() -> None:
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
    op.add_column(
        "showcase_scenes",
        sa.Column("variant_selections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "showcase_scenes",
        sa.Column("showcase_bundle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
