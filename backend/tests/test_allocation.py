"""
tests/test_allocation.py — Randomização + alocação oculta, ponta a ponta.

Prova as DUAS propriedades inegociáveis:
  (1) reprodutibilidade: a mesma semente recria a mesma sequência (auditável);
  (2) o braço NUNCA vaza por API (nem na alocação, nem em /research), embora o
      servidor o conheça internamente para resolver o áudio da sessão.
Cobre ainda: 409 (duplicado), 404 (inexistente), 403 (papel errado), 401 (sem token).
"""
from __future__ import annotations
import datetime as dt
from app.core.models import Participant, StaffUser, Screening, ConsentRecord
from app.core import auth
from app.modules.allocation.randomization import generate_sequence, arm_for_index
from app.modules.allocation.service import allocate_participant, resolve_arm

ALLOC_URL = "/v1/allocation"


def _seed_allocatable(TestSession, code):
    """Participante que passou pelo funil (C2): triado elegível + consentimento aceito."""
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Screening(participant_id=p.id, eligible=True, criteria={"version": "1.0.0"}))
        s.add(ConsentRecord(participant_id=p.id, tcle_version="1.0.0", accepted=True,
                            accepted_at=dt.datetime.now(dt.timezone.utc), content_hash="0" * 64))
        s.commit()
        return p.id


def _researcher_headers(TestSession, email="enroll@uninta.edu.br"):
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password("Senha-Forte-123"),
                      role="researcher", mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), 'researcher')}"}


def _seed_participant(TestSession, code):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit()
        return p.id


# (1) Reprodutibilidade e balanceamento (lógica pura)
def test_sequence_reproducible_and_balanced():
    a = generate_sequence(16, 4, "seed-S")
    b = generate_sequence(16, 4, "seed-S")
    assert a == b                                   # mesma semente → mesma sequência
    assert generate_sequence(16, 4, "outra") != a   # semente diferente → diverge
    assert a.count("A") == 8 and a.count("B") == 8   # balanceado global
    assert all(a[i:i + 4].count("A") == 2 for i in range(0, 16, 4))  # 2A/2B por bloco


# (1b) O serviço aloca na ordem exata da sequência determinística
def test_service_matches_deterministic_sequence(api):
    _client, TestSession = api
    seed, block = "fixed-seed", 4
    expected = generate_sequence(6, block, seed)
    with TestSession() as s:
        pids = []
        for i in range(6):
            p = Participant(study_code=f"P{i}"); s.add(p); s.flush(); pids.append(p.id)
        arms = [allocate_participant(s, pid, seed=seed, block_size=block).arm_coded for pid in pids]
        s.commit()
    assert arms == expected


# (2) A alocação NUNCA revela o braço — mas o servidor o conhece internamente
def test_endpoint_allocates_without_leaking_arm(api):
    client, TestSession = api
    hdr = _researcher_headers(TestSession)
    pid = _seed_allocatable(TestSession, "P-A")
    r = client.post(ALLOC_URL, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 201
    body = r.json()
    assert set(body.keys()) == {"status", "block"} and body["status"] == "allocated"
    blob = str(body)
    assert "'A'" not in blob and "'B'" not in blob and "arm" not in blob.lower()
    # resolução interna (para o áudio da sessão) conhece o braço — sem expô-lo
    with TestSession() as s:
        assert resolve_arm(s, pid) in ("A", "B")


# (2b) Nenhum outro endpoint (pesquisa) expõe o braço
def test_research_endpoint_has_no_arm(api):
    client, TestSession = api
    hdr = _researcher_headers(TestSession)
    r = client.get("/v1/research/participants", headers=hdr)
    assert r.status_code == 200 and "arm" not in str(r.json()).lower()


def test_duplicate_allocation_409(api):
    client, TestSession = api
    hdr = _researcher_headers(TestSession)
    pid = _seed_allocatable(TestSession, "P-DUP")
    assert client.post(ALLOC_URL, headers=hdr, json={"participant_id": str(pid)}).status_code == 201
    r2 = client.post(ALLOC_URL, headers=hdr, json={"participant_id": str(pid)})
    assert r2.status_code == 409


def test_unknown_participant_404(api):
    client, TestSession = api
    hdr = _researcher_headers(TestSession)
    r = client.post(ALLOC_URL, headers=hdr, json={"participant_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404


def test_participant_token_forbidden_403(api):
    client, TestSession = api
    pid = _seed_participant(TestSession, "P-SELF")
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    r = client.post(ALLOC_URL, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 403          # participante não pode se alocar


def test_no_token_401(api):
    client, TestSession = api
    pid = _seed_participant(TestSession, "P-NT")
    r = client.post(ALLOC_URL, json={"participant_id": str(pid)})
    assert r.status_code == 401
