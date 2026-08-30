"""audio_protocol: taxa de amostragem e rampas por protocolo (ADR-100)

O estímulo do protocolo aprovado tem 20 min, 48 kHz e rampas ASSIMÉTRICAS (30 s de
entrada, 60 s de saída). Esses três parâmetros estavam em constantes do módulo de
render, o que tinha duas consequências ruins: a linha do banco não determinava o
artefato por inteiro (auditoria incompleta) e trocar uma constante mudaria em silêncio
o áudio de um protocolo já validado. Passam a viver na linha.

Linhas existentes recebem os valores que já estavam em vigor (44,1 kHz e 3 s/3 s), de
modo que nenhum protocolo já materializado muda de conteúdo.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-29 21:40:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('audio_protocol', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sample_rate', sa.Integer(), nullable=False,
                                      server_default=sa.text('44100')))
        batch_op.add_column(sa.Column('fade_in_s', sa.Numeric(5, 1), nullable=False,
                                      server_default=sa.text('3.0')))
        batch_op.add_column(sa.Column('fade_out_s', sa.Numeric(5, 1), nullable=False,
                                      server_default=sa.text('3.0')))
        batch_op.create_check_constraint(
            'ck_protocol_render',
            'sample_rate > 0 and fade_in_s >= 0 and fade_out_s >= 0')


def downgrade() -> None:
    with op.batch_alter_table('audio_protocol', schema=None) as batch_op:
        batch_op.drop_constraint('ck_protocol_render', type_='check')
        batch_op.drop_column('fade_out_s')
        batch_op.drop_column('fade_in_s')
        batch_op.drop_column('sample_rate')
