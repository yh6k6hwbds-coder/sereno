"""audit_log append-only NO BANCO (trigger + REVOKE) — defesa em profundidade (ADR-056/085)

Fecha o item C8 do checklist LGPD: até aqui o append-only da auditoria era garantido só no
ORM (contornável por SQL cru). Esta migração instala um **trigger** que aborta UPDATE/DELETE
em ``audit_log`` no próprio banco — valendo mesmo para o dono da tabela no Postgres, que
ignora o ``REVOKE`` (mantido como camada extra). Dialect-aware (Postgres em produção; SQLite
no CI-espelho). DDL centralizada em ``app.core.audit_ddl``.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-20 12:00:00.000000
"""
from alembic import op

from app.core import audit_ddl

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    audit_ddl.install(op.get_bind())


def downgrade() -> None:
    audit_ddl.drop(op.get_bind())
