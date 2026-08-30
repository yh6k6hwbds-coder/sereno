"""segurança: PHQ-9 de triagem/seguimento e ficha de encaminhamento (G5/ADR-102)

O protocolo prevê PHQ-9 com finalidade de SEGURANÇA (não é desfecho) e um fluxo de
encaminhamento formal e documentado quando o item 9 é positivo, o GAD-7 chega a 15 ou há
relato de sofrimento psíquico. Nada disso existia: o item 9 não era coletado, e não havia
onde registrar encaminhamento nem confirmação de acolhimento.

Também acrescenta o status `removed` ao participante — retirado do protocolo pela regra de
segurança. É diferente de `withdrawn` (retirada de consentimento) e de `completed`
(conclusão), e o relato ao CEP conta as três separadamente.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-30 14:20:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(PG_JSONB, "postgresql")
_STATUS_ANTIGO = "status in ('active','withdrawn','completed')"
_STATUS_NOVO = "status in ('active','withdrawn','completed','removed')"


def upgrade() -> None:
    op.create_table(
        'safety_assessment',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('participant_id', sa.Uuid(),
                  sa.ForeignKey('participant.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('moment', sa.String(14), nullable=False),
        sa.Column('phq9_total', sa.SmallInteger(), nullable=True),
        sa.Column('phq9_item9', sa.SmallInteger(), nullable=True),
        sa.Column('gad7_total', sa.SmallInteger(), nullable=True),
        sa.Column('risk_detected', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('reasons', _JSON, nullable=True),
        sa.Column('score_version', sa.String(20), nullable=False),
        sa.Column('rule_version', sa.String(20), nullable=False),
        sa.Column('assessed_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.CheckConstraint("moment in ('triagem','intermediaria','espontanea')",
                           name='ck_safety_moment'),
        sa.CheckConstraint('phq9_total is null or phq9_total between 0 and 27',
                           name='ck_safety_phq9'),
        sa.CheckConstraint('gad7_total is null or gad7_total between 0 and 21',
                           name='ck_safety_gad7'),
    )
    op.create_table(
        'referral',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('participant_id', sa.Uuid(),
                  sa.ForeignKey('participant.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('assessment_id', sa.Uuid(),
                  sa.ForeignKey('safety_assessment.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reasons', _JSON, nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default=sa.text("'aberto'")),
        sa.Column('service', sa.String(24), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column('referred_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('aberto','encaminhado','acolhido')",
                           name='ck_referral_status'),
        sa.CheckConstraint("service is null or service in "
                           "('apoio_institucional','caps','urgencia','outro')",
                           name='ck_referral_service'),
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
    op.drop_table('referral')
    op.drop_table('safety_assessment')
