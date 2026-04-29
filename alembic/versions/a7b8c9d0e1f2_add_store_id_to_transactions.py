"""add store_id to transactions

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('store_id', sa.Integer(), nullable=True))
    op.create_index('ix_transactions_store_id', 'transactions', ['store_id'])
    # Backfill existing transactions from their member's store_id
    op.execute("""
        UPDATE transactions t
        SET store_id = m.store_id
        FROM members m
        WHERE t.member_id = m.id
          AND t.store_id IS NULL
    """)


def downgrade() -> None:
    op.drop_index('ix_transactions_store_id', table_name='transactions')
    op.drop_column('transactions', 'store_id')
