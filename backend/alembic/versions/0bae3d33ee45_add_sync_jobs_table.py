"""add sync_jobs table

Revision ID: 0bae3d33ee45
Revises: d15d41971c85
Create Date: 2026-07-18 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bae3d33ee45'
down_revision: Union[str, None] = 'd15d41971c85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sync_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column(
            'status',
            sa.Enum('QUEUED', 'PROCESSING', 'DONE', 'FAILED', name='jobstatus'),
            nullable=False,
        ),
        sa.Column('repo_id', sa.Integer(), sa.ForeignKey('repos.id'), nullable=True),
        sa.Column('pending_approvals', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('sync_jobs')
