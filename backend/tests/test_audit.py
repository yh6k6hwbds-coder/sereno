"""
tests/test_audit.py — Trilha de auditoria append-only (fatia C1), ponta a ponta.

Prova o "Pronto (DoD)":
  - cada ação sensível implementada grava um evento (consentimento, alocação);
  - o evento de alocação NUNCA contém o braço (arm_coded), preservando o cegamento;
  - append-only: UPDATE/DELETE em audit_log é barrado (invariante de serviço no ORM;
    em produção também por GRANT no Postgres — ver ADR-056);
  - leitura só por admin (audit:read): 403 para pesquisador/participante, 401 sem token;
  - resposta de leitura não vaza PII nem o braço; paginação keyset por cursor.
"""
from __future__ import annotations
import datetime as dt
import pytest
from sqlalchemy import select, func

from app.core.models import Participant, StaffUser, AuditLog, Screening, ConsentRecord
from app.core import auth
from app.modules.consent.router import TCLE_CURRENT   # versao vigente do termo (nao literal)
from app.modules.audit.service import record_event, list_events, AuditAppendOnlyError

CONSENT_URL = "/v1/participants/me/consent"
ALLOC_URL = "/v1/allocation"
AUDIT_URL = "/v1/research/audit"
# Termos que revelariam o braço/condição ou seriam PII — não podem aparecer na trilha.
FORBIDDEN = ("arm", "active", "sham", "ativo", "beat", "condition")


def _participant(TestSession, code="P-AUD"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _staff(TestSession, role, email=None):
    email = email or f"{role}@uninta.edu.br"
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return uid, {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def test_consent_records_audit_event(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession)
    assert client.post(CONSENT_URL, headers=hdr,
                       json={"tcle_version": TCLE_CURRENT, "accepted": True}).status_code == 201
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "consent.recorded")).one()
        assert ev.actor_type == "participant" and ev.actor_id == pid
        assert ev.resource_type == "consent_record"
        assert ev.meta == {"tcle_version": TCLE_CURRENT, "accepted": True}


def test_allocation_records_audit_event_without_arm(api):
    client, TestSession = api
    _uid, staff_hdr = _staff(TestSession, "researcher")
    pid, _ = _participant(TestSession, "P-ALLOC")
    # Funil (C2): triado elegível + consentimento, pré-condição da alocação.
    with TestSession() as s:
        s.add(Screening(participant_id=pid, eligible=True, criteria={"version": "1.0.0"}))
        s.add(ConsentRecord(participant_id=pid, tcle_version=TCLE_CURRENT, accepted=True,
                            accepted_at=dt.datetime.now(dt.timezone.utc), content_hash="0" * 64))
        s.commit()
    assert client.post(ALLOC_URL, headers=staff_hdr,
                       json={"participant_id": str(pid)}).status_code == 201
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "allocation.created")).one()
        assert ev.actor_type == "staff" and ev.resource_type == "allocation"
        # INEGOCIÁVEL: o braço não aparece na trilha — só metadado neutro (bloco).
        assert set(ev.meta.keys()) == {"block"}
        assert "arm" not in str(ev.meta).lower()
        blob = f"{ev.action}{ev.resource_type}{ev.meta}".lower()
        assert not any(tok in blob for tok in FORBIDDEN)


def test_read_audit_as_admin_200(api):
    client, TestSession = api
    pid, phdr = _participant(TestSession)
    client.post(CONSENT_URL, headers=phdr, json={"tcle_version": TCLE_CURRENT, "accepted": True})
    _uid, admin_hdr = _staff(TestSession, "admin")
    r = client.get(AUDIT_URL, headers=admin_hdr)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list) and len(body["items"]) >= 1
    ev = body["items"][0]
    assert {"id", "action", "resource_type", "actor_type", "occurred_at"} <= set(ev.keys())
    # Nenhum termo que revele braço/condição na resposta.
    assert not any(tok in str(body).lower() for tok in FORBIDDEN)


def test_read_audit_forbidden_for_researcher_403(api):
    client, TestSession = api
    _uid, hdr = _staff(TestSession, "researcher")
    assert client.get(AUDIT_URL, headers=hdr).status_code == 403


def test_read_audit_forbidden_for_participant_403(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession)
    assert client.get(AUDIT_URL, headers=hdr).status_code == 403


def test_read_audit_no_token_401(api):
    client, _ = api
    assert client.get(AUDIT_URL).status_code == 401


def test_audit_is_append_only(api):
    _client, TestSession = api
    with TestSession() as s:
        ev = record_event(s, action="test.event", resource_type="probe", actor_type="system")
        s.commit(); eid = ev.id

    # UPDATE barrado
    with TestSession() as s:
        row = s.get(AuditLog, eid)
        row.action = "tampered"
        with pytest.raises(AuditAppendOnlyError):
            s.flush()
        s.rollback()

    # DELETE barrado
    with TestSession() as s:
        row = s.get(AuditLog, eid)
        s.delete(row)
        with pytest.raises(AuditAppendOnlyError):
            s.flush()
        s.rollback()

    # O registro segue lá, intacto.
    with TestSession() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.id == eid)) == 1
        assert s.get(AuditLog, eid).action == "test.event"


def test_audit_keyset_pagination(api):
    _client, TestSession = api
    with TestSession() as s:
        for i in range(3):
            record_event(s, action=f"e{i}", resource_type="probe", actor_type="system")
        s.commit()
    with TestSession() as s:
        page1, cur1 = list_events(s, limit=2)
        assert len(page1) == 2 and cur1 is not None
        page2, cur2 = list_events(s, limit=2, cursor=cur1)
        assert len(page2) == 1 and cur2 is None
        ids = {e.id for e in page1} | {e.id for e in page2}
        assert len(ids) == 3          # sem sobreposição entre páginas
