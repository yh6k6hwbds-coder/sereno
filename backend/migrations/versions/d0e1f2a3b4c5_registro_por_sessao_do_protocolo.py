"""session: interrupções com duração, volume médio/máximo e relaxamento 0–10 (G10, ADR-107)

O protocolo, em "Registro e monitoramento", lista o que a plataforma registrará para cada
sessão: horário de início e término, tempo efetivo de reprodução, **interrupções e sua
duração**, **volume médio e máximo**, resultado da verificação de fones e **resposta a um
item único de percepção de relaxamento em escala numérica de 0 a 10**. Três desses itens
não tinham coluna: só a CONTAGEM de interrupções era gravada (não a duração), o volume
aparecia apenas como o ganho declarado no início (não como médio/máximo efetivamente
aplicados) e o item de relaxamento existia somente dentro do questionário pós-sessão, que é
opcional e usa escala de 0 a 4.

Todas anuláveis: sessões anteriores à mudança não têm o dado, e a ausência é informação —
preencher com zero faria parecer que ninguém pausou e que o relaxamento foi o mínimo.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-31 18:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('paused_seconds', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('gain_mean', sa.Numeric(4, 3), nullable=True))
        batch_op.add_column(sa.Column('gain_peak', sa.Numeric(4, 3), nullable=True))
        batch_op.add_column(sa.Column('relaxation_0_10', sa.SmallInteger(), nullable=True))
        batch_op.create_check_constraint(
            'ck_session_gain_mean', 'gain_mean is null or (gain_mean > 0 and gain_mean <= 1)')
        batch_op.create_check_constraint(
            'ck_session_gain_peak', 'gain_peak is null or (gain_peak > 0 and gain_peak <= 1)')
        batch_op.create_check_constraint(
            'ck_session_paused_seconds', 'paused_seconds is null or paused_seconds >= 0')
        batch_op.create_check_constraint(
            'ck_session_relaxation_0_10',
            'relaxation_0_10 is null or relaxation_0_10 between 0 and 10')


def downgrade() -> None:
    with op.batch_alter_table('session', schema=None) as batch_op:
        batch_op.drop_constraint('ck_session_relaxation_0_10', type_='check')
        batch_op.drop_constraint('ck_session_paused_seconds', type_='check')
        batch_op.drop_constraint('ck_session_gain_peak', type_='check')
        batch_op.drop_constraint('ck_session_gain_mean', type_='check')
        batch_op.drop_column('relaxation_0_10')
        batch_op.drop_column('gain_peak')
        batch_op.drop_column('gain_mean')
        batch_op.drop_column('paused_seconds')
