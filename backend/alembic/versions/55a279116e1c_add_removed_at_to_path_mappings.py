"""add removed_at to path_mappings

Revision ID: 55a279116e1c
Revises: 53e39daf459f
Create Date: 2026-07-19 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55a279116e1c'
down_revision: Union[str, None] = '53e39daf459f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('path_mappings', sa.Column('removed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('path_mappings', 'removed_at')
