"""add company_name driver_name license_plate to members

Revision ID: a1b2c3d4e5f6
Revises: 84bd1fde1d2a
Create Date: 2026-04-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '84bd1fde1d2a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('members', sa.Column('company_name', sa.String(), nullable=True))
    op.add_column('members', sa.Column('driver_name', sa.String(), nullable=True))
    op.add_column('members', sa.Column('license_plate', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('members', 'license_plate')
    op.drop_column('members', 'driver_name')
    op.drop_column('members', 'company_name')
