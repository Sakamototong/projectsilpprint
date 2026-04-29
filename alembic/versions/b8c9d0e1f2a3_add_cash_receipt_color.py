"""add cash_receipt_color to stores

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stores', sa.Column('cash_receipt_color', sa.String(7), nullable=True))


def downgrade():
    op.drop_column('stores', 'cash_receipt_color')
