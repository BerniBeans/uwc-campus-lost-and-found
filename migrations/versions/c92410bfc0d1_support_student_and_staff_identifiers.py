"""Support student and staff user identifiers.

Revision ID: c92410bfc0d1
Revises: 6a3e9b1c4d20

Existing student_number values are retained as uwc_identifier. Existing
accounts are designated STUDENT because the old database did not record an
identifier type. This migration uses Alembic batch operations to work on
SQLite (local development) and PostgreSQL (deployment).
"""

from alembic import op
import sqlalchemy as sa


revision = "c92410bfc0d1"
down_revision = "6a3e9b1c4d20"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_student_number")
        batch_op.alter_column(
            "student_number",
            new_column_name="uwc_identifier",
            existing_type=sa.String(length=30),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column("identifier_type", sa.String(length=20), nullable=True)
        )

    # Preserve existing test accounts, without guessing which are staff.
    op.execute("UPDATE users SET identifier_type = 'STUDENT'")

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "identifier_type",
            existing_type=sa.String(length=20),
            nullable=False,
        )
        batch_op.create_index(
            "ix_users_uwc_identifier", ["uwc_identifier"], unique=True
        )


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_uwc_identifier")
        batch_op.drop_column("identifier_type")
        batch_op.alter_column(
            "uwc_identifier",
            new_column_name="student_number",
            existing_type=sa.String(length=30),
            existing_nullable=False,
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.create_index(
            "ix_users_student_number", ["student_number"], unique=True
        )
