"""
tests/test_outcomes.py — Diário de sono e questionário pós-sessão, ponta a ponta.

Diário: registro por dia, duplicata (409), validação (422), RBAC (staff → 403), 401.
Pós-sessão: envio ligado à sessão do próprio participante, duplicata (409),
IDOR (404 em sessão alheia), validação (422), 401.
"""
from __future__ import annotations
import hashlib
import uuid
from sqlalchemy import select
from app.core.models import Participant, Allocation, AudioProtocol, SleepDiary, PostSessionSurvey
from app.core import auth

DIARY = "/v1/diary"
SESSIONS = "/v1/sessions"


def _participant(TestSession, code, arm="A"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _seed_active_alpha(TestSession):
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="px-1", version="1.0.0", band="alpha", carrier_hz=200,
                            beat_hz=10, duration_s=1200, target_peak_dbfs=-3.0,
                            content_hash=hashlib.sha256(b"a").hexdigest()))
        s.commit()


# -------------------- Diário de sono --------------------
def test_diary_entry_ok_and_persists(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-D1")
    r = client.post(DIARY, headers=hdr, json={"diary_date": "2026-03-10", "latency_min": 25,
                                              "awakenings": 2, "duration_h": 6.5, "quality": 3})
    assert r.status_code == 201
    with TestSession() as s:
        rec = s.scalars(select(SleepDiary).where(SleepDiary.participant_id == pid)).one()
        assert str(rec.diary_date) == "2026-03-10" and rec.latency_min == 25 and float(rec.duration_h) == 6.5


def test_diary_duplicate_day_409(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-D2")
    payload = {"diary_date": "2026-03-11", "quality": 2}
    assert client.post(DIARY, headers=hdr, json=payload).status_code == 201
    assert client.post(DIARY, headers=hdr, json=payload).status_code == 409


def test_diary_validation_422(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-D3")
    r = client.post(DIARY, headers=hdr, json={"diary_date": "2026-03-12", "quality": 9})  # 9 fora de 0–4
    assert r.status_code == 422


def test_diary_staff_role_forbidden_403(api):
    client, TestSession = api
    hdr = {"Authorization": f"Bearer {auth.issue_access('11111111-1111-1111-1111-111111111111', 'researcher')}"}
    r = client.post(DIARY, headers=hdr, json={"diary_date": "2026-03-13"})
    assert r.status_code == 403


def test_diary_no_token_401(api):
    client, _ = api
    assert client.post(DIARY, json={"diary_date": "2026-03-14"}).status_code == 401


# -------------------- Questionário pós-sessão --------------------
def _start_session(client, hdr):
    return client.post(SESSIONS, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": True}).json()["session_id"]


def test_survey_ok_and_persists(api):
    client, TestSession = api
    _seed_active_alpha(TestSession)
    _pid, hdr = _participant(TestSession, "P-S1")
    sid = _start_session(client, hdr)
    r = client.post(f"{SESSIONS}/{sid}/survey", headers=hdr,
                    json={"feeling": 3, "relaxation": 4, "liked": 3, "intensity": 2, "would_repeat": True})
    assert r.status_code == 201
    with TestSession() as s:
        rec = s.scalars(select(PostSessionSurvey).where(PostSessionSurvey.session_id == uuid.UUID(sid))).one()
        assert rec.relaxation == 4 and rec.would_repeat is True


def test_survey_duplicate_409(api):
    client, TestSession = api
    _seed_active_alpha(TestSession)
    _pid, hdr = _participant(TestSession, "P-S2")
    sid = _start_session(client, hdr)
    body = {"feeling": 2, "relaxation": 2, "liked": 2, "intensity": 2, "would_repeat": False}
    assert client.post(f"{SESSIONS}/{sid}/survey", headers=hdr, json=body).status_code == 201
    assert client.post(f"{SESSIONS}/{sid}/survey", headers=hdr, json=body).status_code == 409


def test_survey_idor_other_session_404(api):
    client, TestSession = api
    _seed_active_alpha(TestSession)
    _pa, hdr_a = _participant(TestSession, "P-OWN", "A")
    _pb, hdr_b = _participant(TestSession, "P-INT", "B")
    sid = _start_session(client, hdr_a)
    r = client.post(f"{SESSIONS}/{sid}/survey", headers=hdr_b,
                    json={"feeling": 1, "relaxation": 1, "liked": 1, "intensity": 1, "would_repeat": False})
    assert r.status_code == 404


def test_survey_validation_422(api):
    client, TestSession = api
    _seed_active_alpha(TestSession)
    _pid, hdr = _participant(TestSession, "P-S3")
    sid = _start_session(client, hdr)
    r = client.post(f"{SESSIONS}/{sid}/survey", headers=hdr,
                    json={"feeling": 7, "relaxation": 4, "liked": 3, "intensity": 2, "would_repeat": True})
    assert r.status_code == 422
