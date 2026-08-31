"""descontinuação de protocolo e avaliação intermediária T2 (G6/ADR-106)

O protocolo lista critérios de descontinuação — pedido do participante, evento adverso que
contraindique a continuidade e adesão inferior a 50% das sessões previstas ao final da 2ª
semana — e determina que quem descontinua **permanece na análise por intenção de tratar**.
Não havia onde registrar nada disso: o sistema só distinguia ativo, retirado por consentimento,
retirado por segurança e concluído.

Acrescenta a tabela `protocol_discontinuation` (uma por participante, sem texto livre) e o
status `discontinued`, que é diferente de `withdrawn` justamente por continuar na análise.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-31 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None

_STATUS_ANTIGO = "status in ('active','withdrawn','completed','removed')"
_STATUS_NOVO = "status in ('active','withdrawn','completed','removed','discontinued')"


def upgrade() -> None:
    op.create_table(
        'protocol_discontinuation',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('participant_id', sa.Uuid(),
                  sa.ForeignKey('participant.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('reason', sa.String(24), nullable=False),
        sa.Column('adverse_event_id', sa.Uuid(),
                  sa.ForeignKey('adverse_event.id', ondelete='SET NULL'), nullable=True),
        sa.Column('study_week', sa.SmallInteger(), nullable=True),
        sa.Column('sessions_completed', sa.Integer(), nullable=True),
        sa.Column('sessions_prescribed', sa.Integer(), nullable=True),
        sa.Column('kept_in_itt', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('decided_by', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.UniqueConstraint('participant_id', name='uq_discontinuation_participant'),
        sa.CheckConstraint("reason in ('solicitacao_participante','evento_adverso',"
                           "'adesao_insuficiente')", name='ck_discontinuation_reason'),
    )
    # O CHECK do status precisa ser recriado (SQLite reconstrói a tabela; Postgres troca a
    # constraint). batch_alter_table cobre os dois.
    with op.batch_alter_table('participant', schema=None) as batch_op:
        batch_op.drop_constraint('ck_participant_status', type_='check')
        batch_op.create_check_constraint('ck_participant_status', _STATUS_NOVO)


def downgrade() -> None:
    with op.batch_alter_table('participant', schema=None) as batch_op:
        batch_op.drop_constraint('ck_participant_status', type_='check')
        batch_op.create_check_constraint('ck_participant_status', _STATUS_ANTIGO)
    op.drop_table('protocol_discontinuation')
