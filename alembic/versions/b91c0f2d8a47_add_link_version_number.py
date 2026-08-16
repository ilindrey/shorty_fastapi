"""Add optimistic-lock version numbers to links.

Revision ID: b91c0f2d8a47
Revises: a58b4273396c
Create Date: 2026-08-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b91c0f2d8a47'
down_revision: str | None = 'a58b4273396c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the non-null aggregate version used for optimistic locking."""
    op.add_column(
        'links',
        sa.Column(
            'version_number',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove optimistic-lock versions from links."""
    op.drop_column('links', 'version_number')
