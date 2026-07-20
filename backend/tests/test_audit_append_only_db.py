"""
tests/test_audit_append_only_db.py — Append-only da auditoria NO BANCO (ADR-056/085).

O guard do ORM (test_audit já cobre) barra UPDATE/DELETE via sessão; mas SQL cru o
contornaria. Aqui provamos a **segunda camada**: o trigger instalado no banco
(``core/audit_ddl.py``) aborta UPDATE/DELETE em ``audit_log`` mesmo por SQL cru — o
enforcement é exercido no SQLite da suíte (em produção, o mesmo trigger roda no Postgres).
  (1) INSERT de auditoria continua permitido;
  (2) UPDATE cru é recusado pelo banco e a linha permanece intacta;
  (3) DELETE cru é recusado pelo banco e a linha permanece.
"""
from __future__ import annotations
import uuid

import pytest
from sqlalchemy import select, text
import sqlalchemy.exc as sa_exc

from app.core.models import AuditLog


def _seed_event(TestSession) -> uuid.UUID:
    """Insere uma linha de auditoria (INSERT é permitido) e devolve seu id."""
    with TestSession() as s:
        ev = AuditLog(action="consent.recorded", resource_type="participant",
                      actor_type="staff", actor_id=uuid.uuid4(), resource_id=uuid.uuid4(),
                      meta={"k": "v"})
        s.add(ev); s.commit(); eid = ev.id
    return eid


def test_insert_is_allowed(api):
    _client, TestSession = api
    eid = _seed_event(TestSession)
    with TestSession() as s:
        assert s.get(AuditLog, eid) is not None


def test_raw_update_is_rejected_by_db(api):
    _client, TestSession = api
    eid = _seed_event(TestSession)
    # SQL cru (fora do ORM) — só o trigger no banco defende aqui. Alvo pela coluna `action`
    # (o `id` UUID é gravado como hex de 32 chars no SQLite; casar por string não bate).
    with pytest.raises(sa_exc.DatabaseError):
        with TestSession() as s:
            s.execute(text("UPDATE audit_log SET action = :a WHERE action = :old"),
                      {"a": "tampered", "old": "consent.recorded"})
            s.commit()
    # A linha permanece com a ação original.
    with TestSession() as s:
        assert s.get(AuditLog, eid).action == "consent.recorded"


def test_raw_delete_is_rejected_by_db(api):
    _client, TestSession = api
    eid = _seed_event(TestSession)
    with pytest.raises(sa_exc.DatabaseError):
        with TestSession() as s:
            s.execute(text("DELETE FROM audit_log WHERE action = :old"),
                      {"old": "consent.recorded"})
            s.commit()
    with TestSession() as s:
        assert s.get(AuditLog, eid) is not None          # não foi apagada


def test_bulk_raw_update_all_rows_rejected(api):
    """UPDATE cru SEM WHERE (tentativa de adulteração em massa) também é barrado."""
    _client, TestSession = api
    _seed_event(TestSession)
    _seed_event(TestSession)
    with pytest.raises(sa_exc.DatabaseError):
        with TestSession() as s:
            s.execute(text("UPDATE audit_log SET action = 'x'"))
            s.commit()
    with TestSession() as s:
        assert s.scalar(select(AuditLog.action).limit(1)) == "consent.recorded"
