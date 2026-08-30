"""add checkout_abandonment failure class

Revision ID: b8224b3eca06
Revises: 33ac97825135
Create Date: 2026-08-30 19:45:11.597831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8224b3eca06'
down_revision: Union[str, Sequence[str], None] = '33ac97825135'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE failureclass ADD VALUE IF NOT EXISTS 'checkout_abandonment'")


def downgrade() -> None:
    """Downgrade schema."""
    pass