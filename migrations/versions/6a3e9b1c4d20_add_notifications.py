"""add persistent user notifications

Revision ID: 6a3e9b1c4d20
Revises: 301c4ae713c2
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa


revision = "6a3e9b1c4d20"
down_revision = "301c4ae713c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("claim_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["ownership_claims.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notifications_claim_id"),
            ["claim_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_is_read"),
            ["is_read"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_user_id"),
            ["user_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_user_id"))
        batch_op.drop_index(batch_op.f("ix_notifications_is_read"))
        batch_op.drop_index(batch_op.f("ix_notifications_claim_id"))

    op.drop_table("notifications")
