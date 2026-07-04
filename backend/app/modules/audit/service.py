"""
modules/audit/service.py — Trilha de auditoria append-only (transversal).

Registra ações sensíveis (consentimento, alocação e, quando implementados, pedido de
exportação e desbloqueio) em ``audit_log``. Invariantes inegociáveis:
  - **APPEND-ONLY:** nunca UPDATE/DELETE. Em produção isso é garantido por GRANT no
    Postgres (REVOKE UPDATE, DELETE em ``audit_log``); aqui, adicionalmente, um guard no
    ORM recusa qualquer tentativa de modificar/excluir uma linha de ``AuditLog`` em
    qualquer sessão (vale também nos testes/SQLite).
  - **SEM PII em claro e SEM o braço (ativo/sham):** o chamador é responsável por passar
    apenas identificadores pseudonimizados (UUID) e metadados neutros.
"""
from __future__ import annotations
import base64
import datetime as dt
import uuid

from sqlalchemy import and_, event, or_, select
from sqlalchemy.orm import Session as OrmSession

from app.core.models import AuditLog


class AuditAppendOnlyError(Exception):
    """Levantado quando se tenta MODIFICAR ou EXCLUIR uma linha de auditoria."""


@event.listens_for(OrmSession, "before_flush")
def _enforce_audit_append_only(session: OrmSession, flush_context, instances) -> None:
    """Guard de invariante: barra UPDATE/DELETE de ``AuditLog`` antes de qualquer flush."""
    for obj in session.dirty:
        if isinstance(obj, AuditLog) and session.is_modified(obj, include_collections=False):
            raise AuditAppendOnlyError("audit_log é append-only: UPDATE não é permitido.")
    for obj in session.deleted:
        if isinstance(obj, AuditLog):
            raise AuditAppendOnlyError("audit_log é append-only: DELETE não é permitido.")


def record_event(db: OrmSession, *, action: str, resource_type: str, actor_type: str,
                 actor_id: uuid.UUID | None = None, resource_id: uuid.UUID | None = None,
                 meta: dict | None = None) -> AuditLog:
    """Grava um evento na MESMA transação da ação (atomicidade: rola atrás junto se falhar).

    ``meta`` deve conter apenas dados neutros — nunca PII em claro nem o braço."""
    entry = AuditLog(
        action=action, resource_type=resource_type, actor_type=actor_type,
        actor_id=actor_id, resource_id=resource_id, meta=meta,
        occurred_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


def _encode_cursor(occurred_at: dt.datetime, id_: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{occurred_at.isoformat()}|{id_}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, id_ = raw.split("|", 1)
    return dt.datetime.fromisoformat(ts), uuid.UUID(id_)


def list_events(db: OrmSession, *, limit: int = 20, cursor: str | None = None
                ) -> tuple[list[AuditLog], str | None]:
    """Lista eventos (mais recentes primeiro) por paginação keyset em (occurred_at, id).

    Retorna ``(itens, próximo_cursor)``; ``próximo_cursor`` é ``None`` na última página."""
    stmt = (select(AuditLog)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(limit + 1))
    if cursor:
        ts, cid = _decode_cursor(cursor)
        stmt = stmt.where(or_(
            AuditLog.occurred_at < ts,
            and_(AuditLog.occurred_at == ts, AuditLog.id < cid),
        ))
    rows = list(db.scalars(stmt).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].occurred_at, rows[-1].id) if has_more else None
    return rows, next_cursor
