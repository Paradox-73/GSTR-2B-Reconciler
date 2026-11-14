"""uploads.unreconciled: 2B sections v1 doesn't reconcile (#74)

Revision ID: 7c2e5d1a9b04
Revises: 3fbfd516a0a4
Create Date: 2026-11-14 10:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c2e5d1a9b04'
down_revision: str | Sequence[str] | None = '3fbfd516a0a4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default: existing uploads simply have no counts
    op.add_column('uploads', sa.Column('unreconciled', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('uploads', 'unreconciled')
