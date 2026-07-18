"""add default_branch to repos

Revision ID: d15d41971c85
Revises: 7235ac9fffe1
Create Date: 2026-07-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd15d41971c85'
down_revision: Union[str, None] = '7235ac9fffe1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so this backfills existing rows to "main" instead of
    # failing on the NOT NULL constraint -- every repo onboarded before this
    # migration was implicitly synced against "main" anyway.
    op.add_column(
        'repos',
        sa.Column('default_branch', sa.String(length=255), nullable=False, server_default='main'),
    )


def downgrade() -> None:
    op.drop_column('repos', 'default_branch')
