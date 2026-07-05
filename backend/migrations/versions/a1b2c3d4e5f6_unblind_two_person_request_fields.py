"""unblind two-person request fields

Adiciona à `allocation` os campos do desbloqueio em DUAS PESSOAS (ADR-075):
o pedido (requested_by/at/justification) fica separado da revelação (unblinded_at,
já existente), permitindo exigir um 2º admin distinto para revelar a condição.

Revision ID: a1b2c3d4e5f6
Revises: 90dacb6be54c
Create Date: 2026-07-05 18:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '90dacb6be54c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('allocation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unblind_requested_by', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('unblind_requested_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('unblind_justification', sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('allocation', schema=None) as batch_op:
        batch_op.drop_column('unblind_justification')
        batch_op.drop_column('unblind_requested_at')
        batch_op.drop_column('unblind_requested_by')
