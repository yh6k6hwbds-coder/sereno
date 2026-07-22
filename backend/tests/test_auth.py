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


def _login_full(client, TestSession, email="pesq@uninta.edu.br", role="researcher"):
    """Faz o login completo de um staff COM MFA ativo e devolve os tokens (access+refresh).

    Reflete a regra nova: MFA é obrigatório, então o único caminho para o acesso pleno é
    senha → desafio → TOTP. Usado pelos testes que precisam de um token de acesso real."""
    _uid, secret = _seed_staff(TestSession, email=email, role=role, mfa=True)
    r1 = client.post("/v1/auth/token", json={"email": email, "password": "Senha-Forte-123"}).json()
    code = pyotp.TOTP(secret).now()
    return client.post("/v1/auth/mfa/verify", json={"mfa_token": r1["mfa_token"], "code": code}).json()


def test_login_without_mfa_requires_enrollment(api):
    """Senha correta mas SEM 2º fator ativo NÃO concede acesso: só token de cadastro de MFA."""
    client, TestSession = api
    _seed_staff(TestSession)   # mfa=False
    r = client.post("/v1/auth/token", json={"email": "pesq@uninta.edu.br", "password": "Senha-Forte-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_enrollment_required"] is True and body["token_type"] == "bearer"
    # nenhum acesso pleno é emitido antes do 2º fator
    assert "access_token" not in body and "refresh_token" not in body
    # o token entregue é de tipo "enroll" (sem escopo), não "access"
    payload = auth.decode_token(body["enrollment_token"], expected_type="enroll")
    assert payload["role"] == "researcher" and payload.get("scope", "") == ""


def test_enrollment_token_cannot_access_protected_endpoint(api):
    """O token de cadastro não abre endpoint protegido (só enroll/confirm de MFA)."""
    client, TestSession = api
    _seed_staff(TestSession, email="adm@uninta.edu.br", role="admin")   # mfa=False
    enroll = client.post("/v1/auth/token",
                         json={"email": "adm@uninta.edu.br", "password": "Senha-Forte-123"}
                         ).json()["enrollment_token"]
    hdr = {"Authorization": f"Bearer {enroll}"}
    # admin normalmente cria staff; com o token de "enroll", é recusado (401, tipo errado)
    r = client.post("/v1/staff", headers=hdr,
                    json={"email": "novo@uninta.edu.br", "role": "researcher", "password": "Senha-Forte-123"})
    assert r.status_code == 401


def test_full_mfa_onboarding(api):
    """Onboarding: login sem MFA → token de cadastro → enroll → confirm → login exige TOTP → acesso."""
    client, TestSession = api
    email = "novo.staff@uninta.edu.br"
    _seed_staff(TestSession, email=email, role="researcher")   # mfa=False
    enroll = client.post("/v1/auth/token",
                         json={"email": email, "password": "Senha-Forte-123"}).json()["enrollment_token"]
    hdr = {"Authorization": f"Bearer {enroll}"}
    # cadastra e confirma o 2º fator usando o token de "enroll"
    secret = client.post("/v1/staff/me/mfa/enroll", headers=hdr).json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert client.post("/v1/staff/me/mfa/confirm", headers=hdr, json={"code": code}
                       ).json()["mfa_enabled"] is True
    # agora o login exige o 2º fator e, com TOTP, concede acesso pleno
    r1 = client.post("/v1/auth/token", json={"email": email, "password": "Senha-Forte-123"}).json()
    assert r1["mfa_required"] is True
    code2 = pyotp.TOTP(secret).now()
    r2 = client.post("/v1/auth/mfa/verify", json={"mfa_token": r1["mfa_token"], "code": code2})
    assert r2.status_code == 200 and "access_token" in r2.json()


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


def test_last_login_recorded_only_on_full_access(api):
    """ADR-090: a coluna existia e a lista de staff a exibia, mas nada a preenchia.

    Registrada só quando o acesso pleno é concedido (mfa/verify): senha correta sem 2º
    fator não é login, e `refresh` não é voltar a entrar."""
    from app.core.models import StaffUser
    client, TestSession = api
    uid, secret = _seed_staff(TestSession, email="ll@uninta.edu.br", role="admin", mfa=True)

    def _last_login():
        with TestSession() as s:
            return s.get(StaffUser, uid).last_login_at

    assert _last_login() is None                       # nasce vazia
    r1 = client.post("/v1/auth/token", json={"email": "ll@uninta.edu.br",
                                             "password": "Senha-Forte-123"})
    assert _last_login() is None                       # só a senha não conta como login
    r2 = client.post("/v1/auth/mfa/verify",
                     json={"mfa_token": r1.json()["mfa_token"], "code": pyotp.TOTP(secret).now()})
    assert r2.status_code == 200
    marcado = _last_login()
    assert marcado is not None

    # Renovar o token não é um novo login (senão sessão esquecida pareceria uso recente).
    client.post("/v1/auth/refresh", json={"refresh_token": r2.json()["refresh_token"]})
    assert _last_login() == marcado


def test_failed_mfa_does_not_record_login(api):
    from app.core.models import StaffUser
    client, TestSession = api
    uid, _secret = _seed_staff(TestSession, email="bad@uninta.edu.br", role="admin", mfa=True)
    r1 = client.post("/v1/auth/token", json={"email": "bad@uninta.edu.br",
                                             "password": "Senha-Forte-123"})
    assert client.post("/v1/auth/mfa/verify",
                       json={"mfa_token": r1.json()["mfa_token"], "code": "000000"}).status_code == 401
    with TestSession() as s:
        assert s.get(StaffUser, uid).last_login_at is None


def test_refresh_issues_new_access(api):
    client, TestSession = api
    tokens = _login_full(client, TestSession)
    r = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and "access_token" in r.json()


def test_rbac_chain_on_research_endpoint(api):
    client, TestSession = api
    tokens = _login_full(client, TestSession)
    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}
    # researcher tem research:read
    assert client.get("/v1/research/participants", headers=hdr).status_code == 200
    # sem token → 401
    assert client.get("/v1/research/participants").status_code == 401
    # token de participante (papel errado) → 403
    part = {"Authorization": f"Bearer {auth.issue_access('00000000-0000-0000-0000-000000000000', 'participant')}"}
    assert client.get("/v1/research/participants", headers=part).status_code == 403
