"""session: evidência da verificação dicótica de fones e ganho travado (G4/G3, ADR-101)

O protocolo exige que, antes de cada sessão, o participante identifique em qual orelha
soou um sinal de teste — e que a sessão não seja liberada em caso de falha. Até aqui o
cliente apenas declarava ter fones (`headphones_ok`), o que não verifica a condição
dicótica de que o fenômeno binaural depende. A evidência da verificação passa a ser
gravada por sessão (`headphone_check`), junto com o ganho digital travado com que o
áudio foi reproduzido (`audio_gain`), que é o registro da exposição.

Ambas as colunas são anuláveis: sessões anteriores à mudança não têm o dado e não devem
ganhar um valor inventado — a ausência é informação.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-30 09:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None

# Mesma variante do modelo: JSON portátil, JSONB nativo no Postgres.
_JSON = sa.JSON().with_variant(PG_JSONB, "postgresql")


def upgrade() -> None:
    with op.batch_alter_table('session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('headphone_check', _JSON, nullable=True))
        batch_op.add_column(sa.Column('audio_gain', sa.Numeric(4, 3), nullable=True))
        batch_op.create_check_constraint(
            'ck_session_audio_gain', 'audio_gain is null or (audio_gain > 0 and audio_gain <= 1)')


def downgrade() -> None:
    with op.batch_alter_table('session', schema=None) as batch_op:
        batch_op.drop_constraint('ck_session_audio_gain', type_='check')
        batch_op.drop_column('audio_gain')
        batch_op.drop_column('headphone_check')
