"""add record_promise_to_pay action type

Revision ID: ac77c8e8b554
Revises: 18b55a0df465
Create Date: 2026-08-30 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac77c8e8b554'
down_revision: Union[str, Sequence[str], None] = '18b55a0df465'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'record_promise_to_pay'")


def downgrade() -> None:
    """Downgrade schema."""
    pass