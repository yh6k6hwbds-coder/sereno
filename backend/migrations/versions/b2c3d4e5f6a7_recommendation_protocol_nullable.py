"""recommendation_log.suggested_protocol nullable (E1/ADR-068)

O guardrail de contraindicação do recomendador produz `no_recommendation` (sem protocolo).
Para registrar esse evento de segurança fielmente em `recommendation_log`, a coluna
`suggested_protocol` passa a aceitar NULL.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-09 16:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('recommendation_log', schema=None) as batch_op:
        batch_op.alter_column('suggested_protocol', existing_type=sa.String(length=40), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('recommendation_log', schema=None) as batch_op:
        batch_op.alter_column('suggested_protocol', existing_type=sa.String(length=40), nullable=False)
