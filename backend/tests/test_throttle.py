"""
tests/test_throttle.py — Rate limiting por IP + revogação de token por jti (fatia D2).

Prova o "Pronto (DoD)":
  - solicitar OTP e login são limitados por IP (429 após o limite; erro também conta);
  - dentro do limite, segue normal;
  - logout revoga o token de acesso (jti na denylist) → o mesmo token passa a dar 401;
  - logout com refresh_token revoga também o refresh → /auth/refresh passa a dar 401;
  - logout exige autenticação (401 sem token).
O estado do limiter/denylist é isolado por teste (fixture autouse no conftest).
"""
from __future__ import annotations
from app.core.models import Participant, StaffUser
from app.core import auth

REQ_OTP = "/v1/auth/participant/request-otp"
LOGIN = "/v1/auth/token"
LOGOUT = "/v1/auth/logout"
REFRESH = "/v1/auth/refresh"
CONSENT = "/v1/participants/me/consent"   # endpoint autenticado p/ exercitar o token


def _participant(TestSession, code="P-TH"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); pid = p.id
    return pid


def _staff(TestSession, email="s@uninta.edu.br"):
    with TestSession() as s:
        s.add(StaffUser(email=email, password_hash=auth.hash_password("Senha-Forte-123"),
                        role="researcher", mfa_enabled=False))
        s.commit()
    return email


def test_request_otp_rate_limited(api, monkeypatch):
    monkeypatch.setenv("OTP_RATE_LIMIT", "2")
    client, TestSession = api
    _participant(TestSession, "P-EXISTS")
    assert client.post(REQ_OTP, json={"study_code": "P-EXISTS"}).status_code == 200
    assert client.post(REQ_OTP, json={"study_code": "P-EXISTS"}).status_code == 200
    r = client.post(REQ_OTP, json={"study_code": "P-EXISTS"})
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/problem+json")


def test_login_rate_limited_counts_failures(api, monkeypatch):
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "2")
    client, TestSession = api
    email = _staff(TestSession)
    # senha errada ainda consome o limite (defesa contra força-bruta)
    assert client.post(LOGIN, json={"email": email, "password": "errada"}).status_code == 401
    assert client.post(LOGIN, json={"email": email, "password": "errada"}).status_code == 401
    assert client.post(LOGIN, json={"email": email, "password": "errada"}).status_code == 429


def test_within_limit_not_blocked(api, monkeypatch):
    monkeypatch.setenv("OTP_RATE_LIMIT", "5")
    client, TestSession = api
    _participant(TestSession, "P-OK")
    for _ in range(5):
        assert client.post(REQ_OTP, json={"study_code": "P-OK"}).status_code == 200


def test_logout_revokes_access_token(api):
    client, TestSession = api
    pid = _participant(TestSession)
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    # o token funciona antes do logout
    assert client.post(CONSENT, headers=hdr,
                       json={"tcle_version": "1.0.0", "accepted": True}).status_code == 201
    assert client.post(LOGOUT, headers=hdr).status_code == 200
    # o MESMO token agora é recusado (jti revogado)
    assert client.post(CONSENT, headers=hdr,
                       json={"tcle_version": "1.0.0", "accepted": True}).status_code == 401


def test_logout_revokes_refresh_token(api):
    client, TestSession = api
    pid = _participant(TestSession)
    access = auth.issue_access(str(pid), "participant")
    refresh = auth.issue_refresh(str(pid), "participant")
    hdr = {"Authorization": f"Bearer {access}"}
    # refresh funciona antes
    assert client.post(REFRESH, json={"refresh_token": refresh}).status_code == 200
    # logout com refresh_token revoga também o refresh
    assert client.post(LOGOUT, headers=hdr, json={"refresh_token": refresh}).status_code == 200
    assert client.post(REFRESH, json={"refresh_token": refresh}).status_code == 401


def test_logout_requires_auth_401(api):
    client, _ = api
    assert client.post(LOGOUT).status_code == 401
