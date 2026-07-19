"""drop dead jobs table

Revision ID: 53e39daf459f
Revises: 18bed6f81ea4
Create Date: 2026-07-19 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53e39daf459f'
down_revision: Union[str, None] = '18bed6f81ea4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Distinct from sync_jobs -- this table was scaffolded early on but never
    # actually used anywhere; confirmed zero rows ever created by any code
    # path. jobstatus enum type is shared with sync_jobs.status, so it's not
    # dropped -- only this table.
    op.drop_table('jobs')


def downgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repo_id', sa.Integer(), nullable=False),
        sa.Column('batch_key', sa.String(length=1024), nullable=False),
        sa.Column(
            'status',
            sa.Enum('QUEUED', 'PROCESSING', 'DONE', 'FAILED', name='jobstatus'),
            nullable=False,
        ),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['repo_id'], ['repos.id']),
        sa.PrimaryKeyConstraint('id'),
    )
