"""
tests/test_screening.py — Triagem/elegibilidade + gate do funil de alocação (fatia C2).

Prova o "Pronto (DoD)":
  - elegível ⇔ todas as inclusões verdadeiras E nenhuma exclusão presente (regra versionada);
  - triagem registrada + auditada (sem PII); uma por participante (409 duplicado);
  - **bloqueio de alocação** antes de triagem, se inelegível, ou sem consentimento (409);
  - alocação liberada após o funil completo (triagem elegível + consentimento).
Cobre as negações: 401/403/404/409/422.
"""
from __future__ import annotations
import datetime as dt
from sqlalchemy import select

from app.core.models import Participant, StaffUser, Screening, ConsentRecord, Allocation, AuditLog
from app.core import auth

SCREEN = "/v1/screening"
ALLOC = "/v1/allocation"


def _staff(TestSession, role="researcher"):
    with TestSession() as s:
        u = StaffUser(email=f"{role}@uninta.edu.br", password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _participant(TestSession, code="P-SC"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); return p.id


def _consent(TestSession, pid, accepted=True):
    with TestSession() as s:
        s.add(ConsentRecord(participant_id=pid, tcle_version="1.0.0", accepted=accepted,
                            accepted_at=dt.datetime.now(dt.timezone.utc), content_hash="0" * 64))
        s.commit()


def _screen(client, hdr, pid, *, eligible=True):
    return client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid),
        "inclusion": {"ok": bool(eligible)}, "exclusion": {}})


# ---------- elegibilidade ----------
def test_eligible_all_inclusions_no_exclusion(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid),
        "inclusion": {"idade_18_60": True, "queixa_alvo": True},
        "exclusion": {"gravidez": False, "epilepsia": False}})
    assert r.status_code == 201 and r.json() == {"status": "screened", "eligible": True}
    with TestSession() as s:
        sc = s.scalars(select(Screening).where(Screening.participant_id == pid)).one()
        assert sc.eligible is True and sc.criteria["version"] == "1.0.0"


def test_ineligible_when_exclusion_present(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid), "inclusion": {"idade_18_60": True}, "exclusion": {"epilepsia": True}})
    assert r.status_code == 201 and r.json()["eligible"] is False


def test_ineligible_when_inclusion_missing(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid), "inclusion": {"idade_18_60": True, "queixa_alvo": False}, "exclusion": {}})
    assert r.status_code == 201 and r.json()["eligible"] is False


def test_screening_is_audited_without_pii(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=True)
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "screening.recorded")).one()
        assert ev.resource_type == "screening" and ev.resource_id == pid and ev.meta == {"eligible": True}


def test_duplicate_screening_409(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    assert _screen(client, hdr, pid).status_code == 201
    assert _screen(client, hdr, pid).status_code == 409


def test_unknown_participant_404(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": "00000000-0000-0000-0000-000000000000", "inclusion": {}, "exclusion": {}})
    assert r.status_code == 404


def test_participant_token_forbidden_403(api):
    client, TestSession = api
    pid = _participant(TestSession)
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    r = client.post(SCREEN, headers=hdr, json={"participant_id": str(pid), "inclusion": {}, "exclusion": {}})
    assert r.status_code == 403


def test_no_token_401(api):
    client, TestSession = api
    pid = _participant(TestSession)
    r = client.post(SCREEN, json={"participant_id": str(pid), "inclusion": {}, "exclusion": {}})
    assert r.status_code == 401


def test_invalid_uuid_422(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    r = client.post(SCREEN, headers=hdr, json={"participant_id": "nao-e-uuid", "inclusion": {}, "exclusion": {}})
    assert r.status_code == 422


# ---------- gate do funil na alocação ----------
def test_allocation_blocked_before_screening(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _consent(TestSession, pid)                       # consentiu, mas não foi triado
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 409 and "triagem" in r.json()["detail"].lower()


def test_allocation_blocked_when_ineligible(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=False); _consent(TestSession, pid)
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 409 and "inelegível" in r.json()["detail"].lower()


def test_allocation_blocked_without_consent(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=True)         # elegível, mas sem consentimento
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 409 and "consentimento" in r.json()["detail"].lower()


def test_allocation_allowed_after_full_funnel(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=True); _consent(TestSession, pid)
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 201 and r.json()["status"] == "allocated"
    with TestSession() as s:
        assert s.scalar(select(Allocation.id).where(Allocation.participant_id == pid)) is not None
