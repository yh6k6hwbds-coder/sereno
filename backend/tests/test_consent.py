"""
tests/test_consent.py — Fatia de TCLE, ponta a ponta, com AUTENTICAÇÃO REAL.

Semeia um participante, emite um token de acesso real (papel participante) e
exercita a cadeia completa: token → RBAC (consent:write) → participante → persistência.
Cobre 201+persistência, 409 (versão errada), 422 (campo faltando), 401 (sem token).
"""
from __future__ import annotations
from sqlalchemy import select, func
from app.core.models import Participant, ConsentRecord
from app.core import auth

CONSENT_URL = "/v1/participants/me/consent"


def _seed_participant_and_headers(TestSession):
    with TestSession() as s:
        p = Participant(study_code="P-TEST")
        s.add(p); s.commit()
        pid = p.id
    token = auth.issue_access(str(pid), "participant")
    return pid, {"Authorization": f"Bearer {token}"}


def test_record_consent_ok_and_persists(api):
    client, TestSession = api
    pid, hdr = _seed_participant_and_headers(TestSession)
    r = client.post(CONSENT_URL, headers=hdr, json={"tcle_version": "1.0.0", "accepted": True})
    assert r.status_code == 201
    body = r.json()
    assert body["accepted"] is True and len(body["content_hash"]) == 64
    with TestSession() as s:
        rec = s.scalars(select(ConsentRecord).where(ConsentRecord.participant_id == pid)).one()
        assert rec.tcle_version == "1.0.0" and rec.accepted is True
        assert rec.content_hash == body["content_hash"]


def test_wrong_tcle_version_conflict(api):
    client, TestSession = api
    _pid, hdr = _seed_participant_and_headers(TestSession)
    r = client.post(CONSENT_URL, headers=hdr, json={"tcle_version": "0.9", "accepted": True})
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")


def test_missing_field_returns_422(api):
    client, TestSession = api
    _pid, hdr = _seed_participant_and_headers(TestSession)
    r = client.post(CONSENT_URL, headers=hdr, json={"tcle_version": "1.0.0"})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_no_token_returns_401(api):
    client, _ = api
    r = client.post(CONSENT_URL, json={"tcle_version": "1.0.0", "accepted": True})
    assert r.status_code == 401


def test_declining_is_recorded(api):
    client, TestSession = api
    pid, hdr = _seed_participant_and_headers(TestSession)
    r = client.post(CONSENT_URL, headers=hdr, json={"tcle_version": "1.0.0", "accepted": False})
    assert r.status_code == 201 and r.json()["accepted"] is False
    with TestSession() as s:
        n = s.scalar(select(func.count()).select_from(ConsentRecord).where(ConsentRecord.participant_id == pid))
        assert n == 1
