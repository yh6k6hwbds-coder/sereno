"""
tests/test_unblind.py — Desbloqueio controlado em DUAS PESSOAS (fatia C5 + ADR-075).

Prova o "Pronto (DoD)":
  - o PEDIDO (passo 1) NÃO revela a condição; só registra a pendência e audita (`unblind.requested`);
  - a APROVAÇÃO (passo 2) por um SEGUNDO admin DISTINTO revela a condição via chave selada e audita
    (`unblind.performed`) SEM a condição em claro;
  - a regra das duas pessoas: o mesmo admin não pode aprovar o próprio pedido (409);
  - aprovar sem pedido pendente → 409; re-pedir/aprovar já desbloqueado → 409;
  - a condição é o ÚNICO dado sensível e só aparece na resposta da aprovação.
Negações: 401 (sem token), 403 (não-admin), 404 (não alocado), 422 (sem justificativa).
"""
from __future__ import annotations
from sqlalchemy import select

from app.core.models import Participant, StaffUser, Allocation, AuditLog
from app.core import auth
from app.modules.sessions.service import condition_for_arm

REQUEST = "/v1/allocation/{}/unblind-request"
APPROVE = "/v1/allocation/{}/unblind-approve"
JUST = "Evento adverso grave exige avaliacao medica do participante."


def _staff(TestSession, role, email=None):
    email = email or f"{role}@uninta.edu.br"
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _two_admins(TestSession):
    """Dois admins DISTINTOS (ids diferentes) para exercer a regra das duas pessoas."""
    return (_staff(TestSession, "admin", "admin1@uninta.edu.br"),
            _staff(TestSession, "admin", "admin2@uninta.edu.br"))


def _allocated(TestSession, code, arm="A"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush(); pid = p.id
        s.add(Allocation(participant_id=pid, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.commit()
    return pid


def test_request_creates_pending_without_revealing(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-REQ", "A")
    r = client.post(REQUEST.format(pid), headers=admin, json={"justification": JUST})
    assert r.status_code == 200
    body = r.json()
    # o pedido NÃO revela a condição
    assert body["status"] == "pending_approval"
    assert "condition" not in body
    with TestSession() as s:
        a = s.scalars(select(Allocation).where(Allocation.participant_id == pid)).one()
        assert a.unblind_requested_at is not None and a.unblinded_at is None  # pendente, não revelado
    # auditoria do pedido, sem a condição
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "unblind.requested")).one()
        assert ev.resource_id == pid
        blob = f"{ev.action}{ev.resource_type}{ev.meta}".lower()
        assert "active" not in blob and "sham" not in blob and "ativo" not in blob


def test_approve_by_second_admin_reveals_and_audits(api):
    client, TestSession = api
    a1, a2 = _two_admins(TestSession)
    pid = _allocated(TestSession, "P-OK", "A")
    assert client.post(REQUEST.format(pid), headers=a1, json={"justification": JUST}).status_code == 200
    r = client.post(APPROVE.format(pid), headers=a2)
    assert r.status_code == 200
    body = r.json()
    assert body["condition"] == condition_for_arm("A") == "active"
    assert body["participant_id"] == str(pid) and body["justification"] == JUST
    with TestSession() as s:
        a = s.scalars(select(Allocation).where(Allocation.participant_id == pid)).one()
        assert a.unblinded_at is not None
    # auditoria da aprovação, SEM a condição em claro
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "unblind.performed")).one()
        assert ev.resource_id == pid and ev.resource_type == "allocation"
        blob = f"{ev.action}{ev.resource_type}{ev.meta}".lower()
        assert "active" not in blob and "sham" not in blob and "ativo" not in blob
        assert ev.meta.get("justification") == JUST


def test_approve_sham_arm(api):
    client, TestSession = api
    a1, a2 = _two_admins(TestSession)
    pid = _allocated(TestSession, "P-SHAM", "B")
    client.post(REQUEST.format(pid), headers=a1, json={"justification": JUST})
    r = client.post(APPROVE.format(pid), headers=a2)
    assert r.status_code == 200 and r.json()["condition"] == condition_for_arm("B") == "sham"


def test_same_admin_cannot_approve_own_request_409(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-SAME", "A")
    client.post(REQUEST.format(pid), headers=admin, json={"justification": JUST})
    # regra das duas pessoas: o solicitante não aprova o próprio pedido
    r = client.post(APPROVE.format(pid), headers=admin)
    assert r.status_code == 409
    with TestSession() as s:                       # continua NÃO revelado
        a = s.scalars(select(Allocation).where(Allocation.participant_id == pid)).one()
        assert a.unblinded_at is None


def test_approve_without_request_409(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-NOREQ", "A")
    assert client.post(APPROVE.format(pid), headers=admin).status_code == 409


def test_double_request_conflicts_409(api):
    client, TestSession = api
    a1, a2 = _two_admins(TestSession)
    pid = _allocated(TestSession, "P-DUP", "A")
    assert client.post(REQUEST.format(pid), headers=a1, json={"justification": JUST}).status_code == 200
    # já há pedido pendente
    assert client.post(REQUEST.format(pid), headers=a2, json={"justification": JUST}).status_code == 409


def test_approve_twice_conflicts_409(api):
    client, TestSession = api
    a1, a2 = _two_admins(TestSession)
    pid = _allocated(TestSession, "P-TWICE", "A")
    client.post(REQUEST.format(pid), headers=a1, json={"justification": JUST})
    assert client.post(APPROVE.format(pid), headers=a2).status_code == 200
    # já desbloqueado
    assert client.post(APPROVE.format(pid), headers=a2).status_code == 409
    assert client.post(REQUEST.format(pid), headers=a1, json={"justification": JUST}).status_code == 409


def test_request_requires_admin_403_for_researcher(api):
    client, TestSession = api
    hdr = _staff(TestSession, "researcher")
    pid = _allocated(TestSession, "P-RES", "A")
    assert client.post(REQUEST.format(pid), headers=hdr, json={"justification": JUST}).status_code == 403
    assert client.post(APPROVE.format(pid), headers=hdr).status_code == 403


def test_request_no_token_401(api):
    client, TestSession = api
    pid = _allocated(TestSession, "P-NT", "A")
    assert client.post(REQUEST.format(pid), json={"justification": JUST}).status_code == 401
    assert client.post(APPROVE.format(pid)).status_code == 401


def test_request_missing_justification_422(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-NOJ", "A")
    assert client.post(REQUEST.format(pid), headers=admin, json={}).status_code == 422
    assert client.post(REQUEST.format(pid), headers=admin, json={"justification": "curta"}).status_code == 422


def test_not_allocated_404(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    with TestSession() as s:                       # participante SEM alocação
        p = Participant(study_code="P-NOALLOC"); s.add(p); s.commit(); pid = p.id
    assert client.post(REQUEST.format(pid), headers=admin, json={"justification": JUST}).status_code == 404
    assert client.post(APPROVE.format(pid), headers=admin).status_code == 404


def test_condition_appears_only_via_approve(api):
    """A condição não vaza por outro endpoint: só a resposta da aprovação a contém."""
    client, TestSession = api
    a1, a2 = _two_admins(TestSession)
    pid = _allocated(TestSession, "P-ONLY", "A")
    client.post(REQUEST.format(pid), headers=a1, json={"justification": JUST})
    # nenhuma trilha de auditoria (nem do pedido) expõe a condição
    with TestSession() as s:
        for ev in s.scalars(select(AuditLog)).all():
            assert "active" not in f"{ev.meta}".lower() and "sham" not in f"{ev.meta}".lower()
    # só a aprovação revela
    r = client.post(APPROVE.format(pid), headers=a2)
    assert r.json()["condition"] in ("active", "sham")
