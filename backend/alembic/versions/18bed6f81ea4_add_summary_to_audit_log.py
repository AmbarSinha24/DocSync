"""add summary to audit_log

Revision ID: 18bed6f81ea4
Revises: e05b5fbf2f27
Create Date: 2026-07-19 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18bed6f81ea4'
down_revision: Union[str, None] = 'e05b5fbf2f27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_log', sa.Column('summary', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('audit_log', 'summary')
