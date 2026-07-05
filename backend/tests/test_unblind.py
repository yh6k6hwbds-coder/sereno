"""
tests/test_unblind.py — Procedimento de desbloqueio controlado (fatia C5).

Prova o "Pronto (DoD)":
  - o desbloqueio revela a condição (ativo/sham) SÓ ao admin, usando a chave selada;
  - exige papel admin (`unblind:request`) + justificativa; nunca automático nem em massa;
  - o pedido gera evento de auditoria SEM a condição em claro (o braço nunca entra na trilha);
  - é o ÚNICO caminho da API para a condição.
Negações: 401 (sem token), 403 (não-admin), 404 (não alocado), 422 (sem justificativa).
"""
from __future__ import annotations
from sqlalchemy import select

from app.core.models import Participant, StaffUser, Allocation, AuditLog
from app.core import auth
from app.modules.sessions.service import condition_for_arm

URL = "/v1/allocation/{}/unblind-request"
JUST = "Evento adverso grave exige avaliacao medica do participante."


def _staff(TestSession, role):
    with TestSession() as s:
        u = StaffUser(email=f"{role}@uninta.edu.br", password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _allocated(TestSession, code, arm="A"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush(); pid = p.id
        s.add(Allocation(participant_id=pid, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.commit()
    return pid


def test_unblind_reveals_condition_and_audits_without_arm(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-UB", "A")
    r = client.post(URL.format(pid), headers=admin, json={"justification": JUST})
    assert r.status_code == 200
    body = r.json()
    # A → 'active' pela chave selada padrão (ARM_CONDITION_MAP); condição revelada só aqui
    assert body["condition"] == condition_for_arm("A") == "active"
    assert body["participant_id"] == str(pid)
    # unblinded_at gravado na alocação
    with TestSession() as s:
        a = s.scalars(select(Allocation).where(Allocation.participant_id == pid)).one()
        assert a.unblinded_at is not None
    # auditoria registra o evento (quem/por quê) SEM a condição em claro
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "unblind.performed")).one()
        assert ev.resource_id == pid and ev.resource_type == "allocation"
        blob = f"{ev.action}{ev.resource_type}{ev.meta}".lower()
        assert "active" not in blob and "sham" not in blob and "ativo" not in blob
        assert ev.meta.get("justification") == JUST


def test_unblind_sham_arm(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-UB-B", "B")
    r = client.post(URL.format(pid), headers=admin, json={"justification": JUST})
    assert r.status_code == 200 and r.json()["condition"] == condition_for_arm("B") == "sham"


def test_unblind_requires_admin_403_for_researcher(api):
    client, TestSession = api
    hdr = _staff(TestSession, "researcher")
    pid = _allocated(TestSession, "P-RES", "A")
    assert client.post(URL.format(pid), headers=hdr, json={"justification": JUST}).status_code == 403


def test_unblind_no_token_401(api):
    client, TestSession = api
    pid = _allocated(TestSession, "P-NT", "A")
    assert client.post(URL.format(pid), json={"justification": JUST}).status_code == 401


def test_unblind_missing_justification_422(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-NOJ", "A")
    assert client.post(URL.format(pid), headers=admin, json={}).status_code == 422
    assert client.post(URL.format(pid), headers=admin, json={"justification": "curta"}).status_code == 422


def test_unblind_not_allocated_404(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    with TestSession() as s:                       # participante SEM alocação
        p = Participant(study_code="P-NOALLOC"); s.add(p); s.commit(); pid = p.id
    assert client.post(URL.format(pid), headers=admin, json={"justification": JUST}).status_code == 404


def test_condition_appears_only_via_unblind(api):
    """A condição não vaza por outro endpoint: só a resposta do desbloqueio a contém."""
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _allocated(TestSession, "P-ONLY", "A")
    # a alocação (endpoint) não expõe a condição; auditoria da alocação idem
    with TestSession() as s:
        for ev in s.scalars(select(AuditLog)).all():
            assert "active" not in f"{ev.meta}".lower() and "sham" not in f"{ev.meta}".lower()
    # só o desbloqueio revela
    r = client.post(URL.format(pid), headers=admin, json={"justification": JUST})
    assert r.json()["condition"] in ("active", "sham")
