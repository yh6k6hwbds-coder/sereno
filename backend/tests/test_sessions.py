"""
tests/test_sessions.py — Sessão + telemetria, ponta a ponta.

Prova central (cegamento): dois participantes em braços OPOSTOS recebem respostas
com a MESMA forma (mesmas chaves, mesmo handle neutro, sem termos que revelem o
braço), enquanto o SERVIDOR resolve internamente áudios diferentes (ativo vs sham).
Cobre ainda: fones não verificados (422), não alocado (409), banda inexistente (409),
encerramento (telemetria), IDOR no complete (404) e ausência de token (401).
"""
from __future__ import annotations
import hashlib
import datetime as dt
import uuid
from sqlalchemy import select
from app.core.models import Participant, Allocation, AudioProtocol, Session as SessionModel
from app.core import auth

START = "/v1/sessions"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _seed_library(TestSession):
    """Biblioteca mínima: alpha ATIVO (beat=10) e alpha SHAM (beat=0)."""
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="px-0001", version="1.0.0", band="alpha",
                            carrier_hz=200, beat_hz=10, duration_s=1200, target_peak_dbfs=-3.0,
                            content_hash=_hash("alpha-active")))
        s.add(AudioProtocol(protocol_id="px-0002", version="1.0.0", band="alpha",
                            carrier_hz=200, beat_hz=0, duration_s=1200, target_peak_dbfs=-3.0,
                            content_hash=_hash("alpha-sham")))
        s.commit()


def _seed_participant(TestSession, code, arm):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="testref"))
        s.commit()
        pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


FORBIDDEN = ("active", "sham", "beat", "arm", "condition", "ativo")  # termos que revelariam o braço


def test_arm_never_leaks_but_server_resolves_internally(api):
    client, TestSession = api
    _seed_library(TestSession)
    pid_a, hdr_a = _seed_participant(TestSession, "P-ARM-A", "A")   # A → active
    pid_b, hdr_b = _seed_participant(TestSession, "P-ARM-B", "B")   # B → sham

    ra = client.post(START, headers=hdr_a, json={"protocol_handle": "alpha", "headphones_ok": True})
    rb = client.post(START, headers=hdr_b, json={"protocol_handle": "alpha", "headphones_ok": True})
    assert ra.status_code == 201 and rb.status_code == 201
    ba, bb = ra.json(), rb.json()

    # (i) MESMA forma: chaves idênticas e handle idêntico (banda neutra)
    assert set(ba.keys()) == set(bb.keys())
    assert ba["protocol_handle"] == bb["protocol_handle"] == "alpha"

    # (ii) Nenhum termo que revele o braço em qualquer das respostas
    for body in (ba, bb):
        blob = str(body).lower()
        assert not any(tok in blob for tok in FORBIDDEN)

    # (iii) content_hash é opaco e difere (arquivos distintos), mas nada revela o braço
    assert ba["content_hash"] != bb["content_hash"]
    assert len(ba["content_hash"]) == 64 and len(bb["content_hash"]) == 64

    # (iv) O SERVIDOR resolveu áudios diferentes: A→ativo (beat>0), B→sham (beat=0)
    with TestSession() as s:
        sess_a = s.scalars(select(SessionModel).where(SessionModel.participant_id == pid_a)).one()
        sess_b = s.scalars(select(SessionModel).where(SessionModel.participant_id == pid_b)).one()
        proto_a = s.get(AudioProtocol, sess_a.protocol_uuid)
        proto_b = s.get(AudioProtocol, sess_b.protocol_uuid)
        assert float(proto_a.beat_hz) > 0 and float(proto_b.beat_hz) == 0
        assert sess_a.protocol_uuid != sess_b.protocol_uuid


def test_headphones_required_422(api):
    client, TestSession = api
    _seed_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-HP", "A")
    r = client.post(START, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": False})
    assert r.status_code == 422 and "fones" in r.json()["title"].lower()


def test_not_allocated_409(api):
    client, TestSession = api
    _seed_library(TestSession)
    with TestSession() as s:                      # participante SEM alocação
        p = Participant(study_code="P-NOALLOC"); s.add(p); s.commit(); pid = p.id
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    r = client.post(START, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": True})
    assert r.status_code == 409


def test_unknown_band_409(api):
    client, TestSession = api
    _seed_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-BAND", "A")
    r = client.post(START, headers=hdr, json={"protocol_handle": "theta", "headphones_ok": True})
    assert r.status_code == 409          # biblioteca não tem 'theta'


def test_complete_records_telemetry(api):
    client, TestSession = api
    _seed_library(TestSession)
    _pid, hdr = _seed_participant(TestSession, "P-DONE", "B")
    sid = client.post(START, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": True}).json()["session_id"]
    r = client.post(f"{START}/{sid}/complete", headers=hdr, json={"effective_seconds": 1180, "interruptions": 1})
    assert r.status_code == 200 and r.json()["effective_seconds"] == 1180
    with TestSession() as s:
        rec = s.get(SessionModel, uuid.UUID(sid))
        assert rec.completed is True and rec.effective_seconds == 1180 and rec.interruptions == 1


def test_complete_other_participants_session_404_idor(api):
    client, TestSession = api
    _seed_library(TestSession)
    _pid_a, hdr_a = _seed_participant(TestSession, "P-OWNER", "A")
    _pid_b, hdr_b = _seed_participant(TestSession, "P-INTRUDER", "B")
    sid = client.post(START, headers=hdr_a, json={"protocol_handle": "alpha", "headphones_ok": True}).json()["session_id"]
    # participante B tenta encerrar a sessão de A → 404 (não vaza existência)
    r = client.post(f"{START}/{sid}/complete", headers=hdr_b, json={"effective_seconds": 100})
    assert r.status_code == 404


def test_no_token_401(api):
    client, TestSession = api
    _seed_library(TestSession)
    r = client.post(START, json={"protocol_handle": "alpha", "headphones_ok": True})
    assert r.status_code == 401
