"""add parent_batch_mapping_id to path_mappings

Revision ID: e05b5fbf2f27
Revises: 0bae3d33ee45
Create Date: 2026-07-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e05b5fbf2f27'
down_revision: Union[str, None] = '0bae3d33ee45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Second self-referential FK on path_mappings, distinct from the existing
    # parent_mapping_id (section -> containing batch page): this one links a
    # batch/page-level mapping to its own structural parent batch (e.g.
    # "backend/lib" -> "backend"), for nesting Confluence pages to match real
    # folder structure. NULL for top-level batches, whose Confluence parent
    # is just the repo's root page.
    op.add_column(
        'path_mappings',
        sa.Column('parent_batch_mapping_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_path_mappings_parent_batch_mapping_id',
        'path_mappings', 'path_mappings',
        ['parent_batch_mapping_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_path_mappings_parent_batch_mapping_id', 'path_mappings', type_='foreignkey')
    op.drop_column('path_mappings', 'parent_batch_mapping_id')
