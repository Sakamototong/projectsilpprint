"""add member_type and tax_id to members

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('members', sa.Column('member_type', sa.String(), nullable=True, server_default='person'))
    op.add_column('members', sa.Column('tax_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('members', 'tax_id')
    op.drop_column('members', 'member_type')
