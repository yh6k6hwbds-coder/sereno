"""
tests/test_recommender_loop.py — Fecho do loop do recomendador (E1/ADR-069).

Cobre a captura de ACEITE (POST /recommendations/{id}/accept): sucesso, decisão única
(409), anti-IDOR (404 para recomendação alheia), inexistente (404); e o relatório de
COERÊNCIA de pesquisa (GET /research/recommendation-coherence): cego, com alinhamento
objetivo→banda e taxa de aceitação, e negação para não-staff (403).
"""
from __future__ import annotations
import hashlib
import uuid

from app.core.models import Participant, Allocation, AudioProtocol, RecommendationLog
from app.core import auth

REC = "/v1/recommendations"
COH = "/v1/research/recommendation-coherence"
SESS = "/v1/sessions"


def _participant(TestSession, code):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _seed_library(TestSession):
    """Biblioteca mínima (banda alfa: ativo beat=10 e sham beat=0) para iniciar sessões."""
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="px-1", version="1.0.0", band="alpha", carrier_hz=200,
                            beat_hz=10, duration_s=1200, target_peak_dbfs=-3.0,
                            content_hash=hashlib.sha256(b"a-active").hexdigest()))
        s.add(AudioProtocol(protocol_id="px-2", version="1.0.0", band="alpha", carrier_hz=200,
                            beat_hz=0, duration_s=1200, target_peak_dbfs=-3.0,
                            content_hash=hashlib.sha256(b"a-sham").hexdigest()))
        s.commit()


def _participant_allocated(TestSession, code, arm="A"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="t"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _recommend(client, hdr, goal="anxiety", **extra):
    r = client.post(REC, headers=hdr, json={"goal": goal, **extra})
    assert r.status_code == 201
    return r.json()["id"]


def test_accept_records_decision(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-ACC")
    rid = _recommend(client, hdr)
    r = client.post(f"{REC}/{rid}/accept", headers=hdr, json={"accepted": True})
    assert r.status_code == 200 and r.json()["accepted"] is True
    with TestSession() as s:
        row = s.get(RecommendationLog, uuid.UUID(rid))
        assert row.accepted is True


def test_reject_records_false(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-REJ")
    rid = _recommend(client, hdr)
    r = client.post(f"{REC}/{rid}/accept", headers=hdr, json={"accepted": False})
    assert r.status_code == 200 and r.json()["accepted"] is False


def test_accept_twice_conflicts_409(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-DUP")
    rid = _recommend(client, hdr)
    assert client.post(f"{REC}/{rid}/accept", headers=hdr, json={"accepted": True}).status_code == 200
    r2 = client.post(f"{REC}/{rid}/accept", headers=hdr, json={"accepted": False})
    assert r2.status_code == 409


def test_accept_other_participants_recommendation_404_idor(api):
    client, TestSession = api
    _pa, ha = _participant(TestSession, "P-OWNER")
    _pb, hb = _participant(TestSession, "P-INTRUDER")
    rid = _recommend(client, ha)                       # recomendação de A
    r = client.post(f"{REC}/{rid}/accept", headers=hb, json={"accepted": True})   # B tenta aceitar
    assert r.status_code == 404


def test_accept_unknown_id_404(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-UNK")
    r = client.post(f"{REC}/{uuid.uuid4()}/accept", headers=hdr, json={"accepted": True})
    assert r.status_code == 404


def test_coherence_report_blind_for_staff(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-COH")
    # 2 de ansiedade (aceita 1) + 1 de sono → todas alinham objetivo→banda.
    r1 = _recommend(client, hdr, goal="anxiety")
    _r2 = _recommend(client, hdr, goal="anxiety")
    _r3 = _recommend(client, hdr, goal="sleep", sleep_issue="onset")
    client.post(f"{REC}/{r1}/accept", headers=hdr, json={"accepted": True})

    staff = {"Authorization": f"Bearer {auth.issue_access(str(uuid.uuid4()), 'researcher')}"}
    r = client.get(COH, headers=staff)
    assert r.status_code == 200
    b = r.json()
    assert b["n"] == 3
    assert b["goal_alignment_rate"] == 100.0        # ruleset coerente com o objetivo
    assert b["acceptance_rate"] == 33.3             # 1 de 3 aceita
    assert b["mean_relaxation_accepted"] is None    # sem vínculo rec→sessão ainda
    # Cego: nenhum termo de braço no relatório.
    assert not any(t in str(b).lower() for t in ("active", "sham", "arm", "condition", "ativo"))


def test_coherence_forbidden_for_participant_403(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-NOPE")
    r = client.get(COH, headers=hdr)
    assert r.status_code == 403


def test_accept_no_token_401(api):
    client, TestSession = api
    r = client.post(f"{REC}/{uuid.uuid4()}/accept", json={"accepted": True})
    assert r.status_code == 401


def test_coherence_relaxation_mean_via_session_link(api):
    client, TestSession = api
    _seed_library(TestSession)
    _pid, hdr = _participant_allocated(TestSession, "P-LINK")
    rid = _recommend(client, hdr, goal="anxiety")
    client.post(f"{REC}/{rid}/accept", headers=hdr, json={"accepted": True})
    # Inicia a sessão declarando a recomendação de origem (vínculo best-effort).
    sid = client.post(SESS, headers=hdr, json={
        "protocol_handle": "alpha", "headphones_ok": True, "recommendation_id": rid}).json()["session_id"]
    client.post(f"{SESS}/{sid}/complete", headers=hdr, json={"effective_seconds": 1000})
    client.post(f"{SESS}/{sid}/survey", headers=hdr, json={
        "feeling": 3, "relaxation": 4, "liked": 3, "intensity": 2, "would_repeat": True})
    # O vínculo foi gravado na recomendação.
    with TestSession() as s:
        assert str(s.get(RecommendationLog, uuid.UUID(rid)).session_id) == sid
    # A coerência agora computa a média de relaxamento das aceitas.
    staff = {"Authorization": f"Bearer {auth.issue_access(str(uuid.uuid4()), 'researcher')}"}
    b = client.get(COH, headers=staff).json()
    assert b["mean_relaxation_accepted"] == 4.0


def test_link_ignores_foreign_recommendation(api):
    client, TestSession = api
    _seed_library(TestSession)
    _pa, ha = _participant_allocated(TestSession, "P-OWN")
    _pb, hb = _participant_allocated(TestSession, "P-OTHER")
    rid = _recommend(client, ha, goal="anxiety")                # recomendação de A
    # B inicia sessão declarando a recomendação de A → sessão OK, mas NÃO vincula (anti-IDOR).
    r = client.post(SESS, headers=hb, json={
        "protocol_handle": "alpha", "headphones_ok": True, "recommendation_id": rid})
    assert r.status_code == 201
    with TestSession() as s:
        assert s.get(RecommendationLog, uuid.UUID(rid)).session_id is None
