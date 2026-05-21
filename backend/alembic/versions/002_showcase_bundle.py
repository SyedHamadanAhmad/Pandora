"""Add showcase_bundle and variant_selections to showcase_scenes."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_showcase_bundle"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "showcase_scenes",
        sa.Column(
            "showcase_bundle",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "showcase_scenes",
        sa.Column(
            "variant_selections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("showcase_scenes", "variant_selections")
    op.drop_column("showcase_scenes", "showcase_bundle")
