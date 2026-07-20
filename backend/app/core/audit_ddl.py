"""
core/audit_ddl.py — Enforcement de ``audit_log`` append-only NO BANCO (defesa em profundidade).

O guard no ORM (``modules/audit/service.py``) barra UPDATE/DELETE que passam pela *sessão*; mas
um ``UPDATE``/``DELETE`` por SQL cru (fora do ORM) o contornaria. Esta camada fecha isso no
próprio banco, com um **trigger** que aborta qualquer UPDATE/DELETE na tabela (ADR-056/085).

**Por que trigger e não só REVOKE:** no PostgreSQL o **dono da tabela ignora** as checagens de
privilégio, então ``REVOKE UPDATE, DELETE`` sozinho não impede o usuário da aplicação (que
costuma ser o dono) de alterar linhas. O trigger vale **independentemente de dono/privilégio**;
o ``REVOKE ... FROM PUBLIC`` fica como camada extra. No SQLite (testes/CI-espelho) o mesmo é
feito com dois triggers ``RAISE(ABORT)`` — assim a invariante é **exercida na suíte**.

Fonte ÚNICA da DDL: usada tanto pela migração quanto pelo listener ``after_create`` (para o
schema de teste montado por ``create_all``). Sem import de modelos aqui (evita ciclo)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

_TABLE = "audit_log"

_PG_INSTALL = [
    """
    CREATE OR REPLACE FUNCTION audit_log_append_only_guard() RETURNS trigger
      LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'audit_log is append-only: % not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
    END;
    $$;
    """,
    "DROP TRIGGER IF EXISTS audit_log_no_mutation ON audit_log;",
    """
    CREATE TRIGGER audit_log_no_mutation
      BEFORE UPDATE OR DELETE ON audit_log
      FOR EACH ROW EXECUTE FUNCTION audit_log_append_only_guard();
    """,
    "REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;",
]
_PG_DROP = [
    "DROP TRIGGER IF EXISTS audit_log_no_mutation ON audit_log;",
    "DROP FUNCTION IF EXISTS audit_log_append_only_guard();",
]

_SQLITE_INSTALL = [
    """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_update
      BEFORE UPDATE ON audit_log
    BEGIN
      SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE not allowed');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
      BEFORE DELETE ON audit_log
    BEGIN
      SELECT RAISE(ABORT, 'audit_log is append-only: DELETE not allowed');
    END;
    """,
]
_SQLITE_DROP = [
    "DROP TRIGGER IF EXISTS audit_log_no_update;",
    "DROP TRIGGER IF EXISTS audit_log_no_delete;",
]


def _statements(dialect: str, *, drop: bool) -> list[str]:
    if dialect == "postgresql":
        return _PG_DROP if drop else _PG_INSTALL
    if dialect == "sqlite":
        return _SQLITE_DROP if drop else _SQLITE_INSTALL
    return []   # outros dialetos: no-op (o guard do ORM segue valendo)


def install(bind: Connection) -> None:
    """Instala o enforcement de append-only no banco (idempotente)."""
    for stmt in _statements(bind.dialect.name, drop=False):
        bind.execute(text(stmt))


def drop(bind: Connection) -> None:
    """Remove o enforcement (downgrade)."""
    for stmt in _statements(bind.dialect.name, drop=True):
        bind.execute(text(stmt))
