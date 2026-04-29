"""add receipt customization columns

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stores', sa.Column('logo_base64', sa.Text(), nullable=True))
    op.add_column('stores', sa.Column('receipt_color', sa.String(7), nullable=True))
    op.add_column('stores', sa.Column('receipt_header_text', sa.Text(), nullable=True))
    op.add_column('stores', sa.Column('receipt_footer_text', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('stores', 'receipt_footer_text')
    op.drop_column('stores', 'receipt_header_text')
    op.drop_column('stores', 'receipt_color')
    op.drop_column('stores', 'logo_base64')
