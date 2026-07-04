"""
tests/test_auth.py — Autenticação de staff, ponta a ponta.

Cobre: login sem MFA → tokens; login com MFA → desafio → verificação TOTP → tokens;
senha errada → 401; refresh; e a cadeia token→RBAC (researcher acessa /research;
participante é barrado 403; sem token → 401).
"""
from __future__ import annotations
import pyotp
from app.core.models import StaffUser
from app.core import auth


def _seed_staff(TestSession, email="pesq@uninta.edu.br", role="researcher",
                password="Senha-Forte-123", mfa=False):
    secret = auth.new_mfa_secret()
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password(password),
                      role=role, mfa_enabled=mfa,
                      mfa_secret=secret.encode() if mfa else None)
        s.add(u); s.commit()
        uid = u.id
    return uid, secret


def test_login_without_mfa_returns_tokens(api):
    client, TestSession = api
    _seed_staff(TestSession)
    r = client.post("/v1/auth/token", json={"email": "pesq@uninta.edu.br", "password": "Senha-Forte-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is False and body["token_type"] == "bearer"
    payload = auth.decode_token(body["access_token"], expected_type="access")
    assert payload["role"] == "researcher"


def test_wrong_password_401_problem_json(api):
    client, TestSession = api
    _seed_staff(TestSession)
    r = client.post("/v1/auth/token", json={"email": "pesq@uninta.edu.br", "password": "errada"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


def test_unknown_user_401_no_enumeration(api):
    client, _ = api
    r = client.post("/v1/auth/token", json={"email": "naoexiste@x.com", "password": "seja-la-o-que-for"})
    assert r.status_code == 401 and r.json()["title"] == "Credenciais inválidas"


def test_mfa_flow(api):
    client, TestSession = api
    _uid, secret = _seed_staff(TestSession, email="admin@uninta.edu.br", role="admin", mfa=True)
    # 1) senha correta → desafio, sem acesso ainda
    r1 = client.post("/v1/auth/token", json={"email": "admin@uninta.edu.br", "password": "Senha-Forte-123"})
    assert r1.status_code == 200 and r1.json()["mfa_required"] is True
    mfa_token = r1.json()["mfa_token"]
    assert "access_token" not in r1.json()
    # 2) código TOTP correto → tokens
    code = pyotp.TOTP(secret).now()
    r2 = client.post("/v1/auth/mfa/verify", json={"mfa_token": mfa_token, "code": code})
    assert r2.status_code == 200 and "access_token" in r2.json()
    # 3) código errado → 401
    r3 = client.post("/v1/auth/mfa/verify", json={"mfa_token": mfa_token, "code": "000000"})
    assert r3.status_code == 401


def test_refresh_issues_new_access(api):
    client, TestSession = api
    _seed_staff(TestSession)
    tokens = client.post("/v1/auth/token", json={"email": "pesq@uninta.edu.br", "password": "Senha-Forte-123"}).json()
    r = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and "access_token" in r.json()


def test_rbac_chain_on_research_endpoint(api):
    client, TestSession = api
    _seed_staff(TestSession)
    tokens = client.post("/v1/auth/token", json={"email": "pesq@uninta.edu.br", "password": "Senha-Forte-123"}).json()
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}
    # researcher tem research:read
    assert client.get("/v1/research/participants", headers=hdr).status_code == 200
    # sem token → 401
    assert client.get("/v1/research/participants").status_code == 401
    # token de participante (papel errado) → 403
    part = {"Authorization": f"Bearer {auth.issue_access('00000000-0000-0000-0000-000000000000', 'participant')}"}
    assert client.get("/v1/research/participants", headers=part).status_code == 403
