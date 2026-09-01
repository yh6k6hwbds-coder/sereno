"""audio_protocol: nível do leito ambiente (G2, ADR-109)

O protocolo, em "Parâmetros comuns aos dois braços", promete "trilha de fundo ambiental de
baixa intensidade, idêntica em conteúdo, duração e nível, sobre a qual os tons são
superpostos". Até aqui o estímulo era só o par de senoides: o leito não existia em lugar
nenhum do sistema.

A coluna é ANULÁVEL porque os protocolos curtos de demo/teste não têm leito, e porque a
ausência é informação — um zero diria "leito no mesmo nível do estímulo", que é o oposto de
"baixa intensidade". O CHECK exige valor negativo pela mesma razão: um leito acima do
estímulo seria mascaramento, que é o que o protocolo recusa.

Não há backfill: a linha do estudo entra com o valor pela migração de dados/seed, e mudar o
leito de um protocolo já auditado é NOVA VERSÃO (novo `content_hash`), nunca um UPDATE.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-01 02:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('audio_protocol', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bed_level_dbr', sa.Numeric(5, 1), nullable=True))
        batch_op.create_check_constraint(
            'ck_protocol_bed_level', 'bed_level_dbr is null or bed_level_dbr < 0')


def downgrade() -> None:
    with op.batch_alter_table('audio_protocol', schema=None) as batch_op:
        batch_op.drop_constraint('ck_protocol_bed_level', type_='check')
        batch_op.drop_column('bed_level_dbr')
