"""staff_setup_token — convite e redefinição de senha de staff (F4.7/ADR-094)

Token de uso único, guardado só como hash, para o staff DEFINIR a própria senha. Nenhuma
linha existente é afetada: a tabela nasce vazia e contas já criadas seguem com senha.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-29 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'staff_setup_token',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('staff_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('purpose', sa.String(length=16), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staff_user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("purpose in ('invite','reset')", name='ck_staff_setup_purpose'),
    )
    with op.batch_alter_table('staff_setup_token', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_staff_setup_token_staff_id'), ['staff_id'],
                              unique=False)
        # O consumo busca pelo HASH (o token em claro só existe no e-mail): sem este índice
        # cada tentativa varreria a tabela — e é endpoint público.
        batch_op.create_index(batch_op.f('ix_staff_setup_token_token_hash'), ['token_hash'],
                              unique=False)


def downgrade() -> None:
    with op.batch_alter_table('staff_setup_token', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_staff_setup_token_token_hash'))
        batch_op.drop_index(batch_op.f('ix_staff_setup_token_staff_id'))
    op.drop_table('staff_setup_token')
