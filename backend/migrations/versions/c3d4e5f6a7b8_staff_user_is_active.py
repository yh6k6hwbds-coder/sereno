"""staff_user.is_active — lifecycle de staff (C3/ADR-081)

Desativar um pesquisador/admin suspende o acesso (login e tokens já emitidos) sem
apagar o registro, preservando a trilha de autoria das ações passadas. Linhas
existentes assumem `true` (ninguém é desativado pela migração).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-20 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('staff_user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False,
                                      server_default=sa.text('true')))


def downgrade() -> None:
    with op.batch_alter_table('staff_user', schema=None) as batch_op:
        batch_op.drop_column('is_active')
