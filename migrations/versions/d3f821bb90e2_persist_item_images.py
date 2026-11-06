"""Store new item photographs in PostgreSQL instead of ephemeral disk.

Revision ID: d3f821bb90e2
Revises: c92410bfc0d1

Existing filenames are preserved and old photographs remain accessible
where legacy files still exist. Missing legacy files cannot be recreated.
"""

from alembic import op
import sqlalchemy as sa


revision = "d3f821bb90e2"
down_revision = "c92410bfc0d1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lost_items") as batch_op:
        batch_op.add_column(sa.Column("image_data", sa.LargeBinary(), nullable=True))
    with op.batch_alter_table("found_items") as batch_op:
        batch_op.add_column(sa.Column("image_data", sa.LargeBinary(), nullable=True))


def downgrade():
    # Downgrading removes photographs uploaded since this revision.
    with op.batch_alter_table("found_items") as batch_op:
        batch_op.drop_column("image_data")
    with op.batch_alter_table("lost_items") as batch_op:
        batch_op.drop_column("image_data")
