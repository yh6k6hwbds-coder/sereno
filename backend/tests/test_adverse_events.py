"""
tests/test_adverse_events.py — Relato de evento adverso, ponta a ponta.

Cobre: leve → registrado sem atenção; grave → atenção + gancho de notificação
acionado; evento ligado à própria sessão (201) vs sessão alheia (404); gravidade
inválida (422); papel errado (403); sem token (401). A resposta sempre orienta ajuda.
"""
from __future__ import annotations
import hashlib
import pytest
from sqlalchemy import select
from app.core.models import Participant, Allocation, AudioProtocol, Session as SessionModel, AdverseEvent
from app.core import auth
from app.modules.adverse_events import router as ae_router

URL = "/v1/adverse-events"
SESSIONS = "/v1/sessions"


@pytest.fixture
def capture_notify(monkeypatch):
    calls = []
    monkeypatch.setattr(ae_router, "notify_team", lambda eid, sev: calls.append((eid, sev)))
    return calls


def _participant(TestSession, code, arm="A"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _seed_alpha(TestSession):
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="px-1", version="1.0.0", band="alpha", carrier_hz=200,
                            beat_hz=10, duration_s=1200, target_peak_dbfs=-3.0,
                            content_hash=hashlib.sha256(b"a").hexdigest()))
        s.commit()


def test_mild_event_recorded_no_attention(api, capture_notify):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-AE1")
    r = client.post(URL, headers=hdr, json={"type": "cefaleia", "severity": "mild"})
    assert r.status_code == 201
    body = r.json()
    assert body["requires_attention"] is False and "profissional" in body["guidance"]
    assert capture_notify == []                       # não notificou
    with TestSession() as s:
        assert s.scalar(select(AdverseEvent.id).where(AdverseEvent.participant_id == pid)) is not None


def test_severe_event_flags_attention_and_notifies(api, capture_notify):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE2")
    r = client.post(URL, headers=hdr, json={"type": "tontura intensa", "severity": "severe"})
    assert r.status_code == 201
    body = r.json()
    assert body["requires_attention"] is True
    assert "192" in body["guidance"]                  # orientação urgente
    assert len(capture_notify) == 1 and capture_notify[0][1] == "severe"


def test_moderate_also_requires_attention(api, capture_notify):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE3")
    r = client.post(URL, headers=hdr, json={"type": "nausea", "severity": "moderate"})
    assert r.status_code == 201 and r.json()["requires_attention"] is True
    assert len(capture_notify) == 1


def test_event_linked_to_own_session_ok(api, capture_notify):
    client, TestSession = api
    _seed_alpha(TestSession)
    _pid, hdr = _participant(TestSession, "P-AE4")
    sid = client.post(SESSIONS, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": True}).json()["session_id"]
    r = client.post(URL, headers=hdr, json={"type": "desconforto", "severity": "mild", "session_id": sid})
    assert r.status_code == 201


def test_event_linked_to_other_session_404(api, capture_notify):
    client, TestSession = api
    _seed_alpha(TestSession)
    _pa, hdr_a = _participant(TestSession, "P-AE-OWN", "A")
    _pb, hdr_b = _participant(TestSession, "P-AE-INT", "B")
    sid = client.post(SESSIONS, headers=hdr_a, json={"protocol_handle": "alpha", "headphones_ok": True}).json()["session_id"]
    r = client.post(URL, headers=hdr_b, json={"type": "cefaleia", "severity": "mild", "session_id": sid})
    assert r.status_code == 404


def test_invalid_severity_422(api, capture_notify):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE5")
    r = client.post(URL, headers=hdr, json={"type": "x", "severity": "gravissimo"})
    assert r.status_code == 422


def test_staff_role_forbidden_403(api, capture_notify):
    client, TestSession = api
    hdr = {"Authorization": f"Bearer {auth.issue_access('22222222-2222-2222-2222-222222222222', 'researcher')}"}
    r = client.post(URL, headers=hdr, json={"type": "x", "severity": "mild"})
    assert r.status_code == 403


def test_no_token_401(api, capture_notify):
    client, _ = api
    assert client.post(URL, json={"type": "x", "severity": "mild"}).status_code == 401
