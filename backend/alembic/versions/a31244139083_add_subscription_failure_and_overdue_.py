"""add subscription_failure and overdue_receivable classes

Revision ID: a31244139083
Revises: ac77c8e8b554
Create Date: 2026-08-31 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a31244139083'
down_revision: Union[str, Sequence[str], None] = 'ac77c8e8b554'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE failureclass ADD VALUE IF NOT EXISTS 'subscription_failure'")
    op.execute("ALTER TYPE failureclass ADD VALUE IF NOT EXISTS 'overdue_receivable'")


def downgrade() -> None:
    """Downgrade schema."""
    pass