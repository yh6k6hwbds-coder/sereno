"""
tests/test_participant_auth.py — Login de participante por e-mail/OTP, ponta a ponta.

Cobre: solicitar OTP (resposta genérica, sem enumeração), verificar com código correto
(→ tokens), código errado (→ 401 + tentativa), código expirado (→ 401), study_code
inexistente (→ 401 genérico), e que o token emitido funciona num endpoint de participante.
Captura o código via monkeypatch da entrega (o código NUNCA vai em claro no banco).
"""
from __future__ import annotations
import datetime as dt
import pytest
from sqlalchemy import select
from app.core.models import Participant, OtpChallenge
from app.core import auth
from app.modules.participant_auth import router as pa_router

REQ = "/v1/auth/participant/request-otp"
VER = "/v1/auth/participant/verify-otp"


@pytest.fixture
def capture_otp(monkeypatch):
    box = {}
    monkeypatch.setattr(pa_router, "deliver_otp", lambda pid, code: box.update(code=code, pid=pid))
    return box


def _seed_participant(TestSession, code="P-OTP"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit()
        return p.id


def test_request_otp_is_generic_no_enumeration(api, capture_otp):
    client, TestSession = api
    _seed_participant(TestSession, "P-EXISTS")
    r_known = client.post(REQ, json={"study_code": "P-EXISTS"})
    r_unknown = client.post(REQ, json={"study_code": "NAO-EXISTE"})
    # mesma resposta para existente e inexistente
    assert r_known.status_code == 200 and r_unknown.status_code == 200
    assert r_known.json() == r_unknown.json()


def test_otp_never_stored_in_plaintext(api, capture_otp):
    client, TestSession = api
    pid = _seed_participant(TestSession)
    client.post(REQ, json={"study_code": "P-OTP"})
    code = capture_otp["code"]
    with TestSession() as s:
        ch = s.scalars(select(OtpChallenge).where(OtpChallenge.participant_id == pid)).one()
        assert ch.code_hash != code and len(ch.code_hash) == 64   # guardado como hash


def test_verify_correct_code_issues_participant_token(api, capture_otp):
    client, TestSession = api
    pid = _seed_participant(TestSession)
    client.post(REQ, json={"study_code": "P-OTP"})
    r = client.post(VER, json={"study_code": "P-OTP", "code": capture_otp["code"]})
    assert r.status_code == 200
    payload = auth.decode_token(r.json()["access_token"], expected_type="access")
    assert payload["role"] == "participant" and payload["sub"] == str(pid)
    # código é de uso único: repetir falha
    assert client.post(VER, json={"study_code": "P-OTP", "code": capture_otp["code"]}).status_code == 401


def test_wrong_code_401_and_counts_attempt(api, capture_otp):
    client, TestSession = api
    pid = _seed_participant(TestSession)
    client.post(REQ, json={"study_code": "P-OTP"})
    r = client.post(VER, json={"study_code": "P-OTP", "code": "000000"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    with TestSession() as s:
        ch = s.scalars(select(OtpChallenge).where(OtpChallenge.participant_id == pid)).one()
        assert ch.attempts == 1 and ch.consumed is False


def test_expired_code_401(api, capture_otp):
    client, TestSession = api
    pid = _seed_participant(TestSession)
    client.post(REQ, json={"study_code": "P-OTP"})
    with TestSession() as s:            # força expiração
        ch = s.scalars(select(OtpChallenge).where(OtpChallenge.participant_id == pid)).one()
        ch.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        s.commit()
    assert client.post(VER, json={"study_code": "P-OTP", "code": capture_otp["code"]}).status_code == 401


def test_unknown_study_code_401_generic(api):
    client, _ = api
    r = client.post(VER, json={"study_code": "NAO-EXISTE", "code": "123456"})
    assert r.status_code == 401 and r.json()["title"] == "Código inválido"


def test_issued_token_works_on_participant_endpoint(api, capture_otp):
    client, TestSession = api
    _seed_participant(TestSession)
    client.post(REQ, json={"study_code": "P-OTP"})
    tokens = client.post(VER, json={"study_code": "P-OTP", "code": capture_otp["code"]}).json()
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/v1/diary", headers=hdr, json={"diary_date": "2026-03-10", "quality": 3})
    assert r.status_code == 201
