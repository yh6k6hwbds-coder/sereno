"""
tests/test_staff.py — Gestão de staff (admin) + cadastro de MFA (fatia C3).

Prova o "Pronto (DoD)":
  - admin cria pesquisador (senha cifrada, nunca em claro); sem auto-registro público
    (403 p/ não-admin, 401 sem token); e-mail único (409); criação auditada sem PII;
  - enrollment de MFA emite `provisioning_uri` (otpauth://) e guarda o segredo, mas só
    ATIVA após confirmar com um código TOTP válido; código errado → 401; participante → 403;
  - com MFA ativo, o login passa a exigir o 2º fator.
Negações: 401/403/409/422.
"""
from __future__ import annotations
import pyotp
from sqlalchemy import select

from app.core.models import StaffUser, AuditLog
from app.core import auth

STAFF = "/v1/staff"
ENROLL = "/v1/staff/me/mfa/enroll"
CONFIRM = "/v1/staff/me/mfa/confirm"
LOGIN = "/v1/auth/token"


def _staff_token(TestSession, role, email=None, password="Senha-Forte-123"):
    email = email or f"{role}@uninta.edu.br"
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password(password),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return uid, email, {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def test_admin_creates_staff(api):
    client, TestSession = api
    _uid, _e, admin = _staff_token(TestSession, "admin")
    r = client.post(STAFF, headers=admin,
                    json={"email": "novo@uninta.edu.br", "role": "researcher", "password": "Senha-Forte-123"})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "novo@uninta.edu.br" and body["role"] == "researcher" and "id" in body
    assert "password" not in str(body).lower() and "senha" not in str(body).lower()
    with TestSession() as s:
        u = s.scalars(select(StaffUser).where(StaffUser.email == "novo@uninta.edu.br")).one()
        assert u.password_hash != "Senha-Forte-123"                      # cifrada
        assert auth.verify_password(u.password_hash, "Senha-Forte-123")  # e válida
        assert u.mfa_enabled is False


def test_duplicate_email_409(api):
    client, TestSession = api
    _uid, _e, admin = _staff_token(TestSession, "admin")
    body = {"email": "dup@uninta.edu.br", "role": "researcher", "password": "Senha-Forte-123"}
    assert client.post(STAFF, headers=admin, json=body).status_code == 201
    assert client.post(STAFF, headers=admin, json=body).status_code == 409


def test_researcher_cannot_create_staff_403(api):
    client, TestSession = api
    _uid, _e, res = _staff_token(TestSession, "researcher")
    r = client.post(STAFF, headers=res,
                    json={"email": "x@uninta.edu.br", "role": "researcher", "password": "Senha-Forte-123"})
    assert r.status_code == 403


def test_no_token_401(api):
    client, _ = api
    r = client.post(STAFF, json={"email": "x@uninta.edu.br", "role": "researcher", "password": "Senha-Forte-123"})
    assert r.status_code == 401


def test_invalid_inputs_422(api):
    client, TestSession = api
    _uid, _e, admin = _staff_token(TestSession, "admin")
    bad = [
        {"email": "sem-arroba", "role": "researcher", "password": "Senha-Forte-123"},  # e-mail
        {"email": "a@b.com", "role": "root", "password": "Senha-Forte-123"},           # papel
        {"email": "a@b.com", "role": "researcher", "password": "curta"},               # senha curta
    ]
    for payload in bad:
        assert client.post(STAFF, headers=admin, json=payload).status_code == 422


def test_staff_creation_is_audited_without_pii(api):
    client, TestSession = api
    _uid, _e, admin = _staff_token(TestSession, "admin")
    client.post(STAFF, headers=admin,
                json={"email": "sigilo@uninta.edu.br", "role": "researcher", "password": "Senha-Forte-123"})
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "staff.created")).one()
        assert ev.resource_type == "staff_user" and ev.meta == {"role": "researcher"}
        assert "sigilo" not in f"{ev.meta}".lower()      # e-mail não entra no log


def test_mfa_enroll_returns_uri_and_stores_secret(api):
    client, TestSession = api
    uid, _e, hdr = _staff_token(TestSession, "researcher", email="m@uninta.edu.br")
    r = client.post(ENROLL, headers=hdr)
    assert r.status_code == 200
    assert r.json()["provisioning_uri"].startswith("otpauth://")
    secret = r.json()["secret"]
    with TestSession() as s:
        u = s.get(StaffUser, uid)
        assert u.mfa_secret == secret.encode() and u.mfa_enabled is False   # ainda não ativo


def test_mfa_confirm_enables_and_login_requires_second_factor(api):
    client, TestSession = api
    _uid, email, hdr = _staff_token(TestSession, "researcher", email="c@uninta.edu.br")
    secret = client.post(ENROLL, headers=hdr).json()["secret"]
    code = pyotp.TOTP(secret).now()
    r = client.post(CONFIRM, headers=hdr, json={"code": code})
    assert r.status_code == 200 and r.json()["mfa_enabled"] is True
    # com MFA ativo, o login não devolve tokens direto: exige o 2º fator
    lr = client.post(LOGIN, json={"email": email, "password": "Senha-Forte-123"})
    assert lr.status_code == 200 and lr.json()["mfa_required"] is True


def test_mfa_confirm_wrong_code_401(api):
    client, TestSession = api
    _uid, _e, hdr = _staff_token(TestSession, "researcher", email="w@uninta.edu.br")
    client.post(ENROLL, headers=hdr)
    assert client.post(CONFIRM, headers=hdr, json={"code": "000000"}).status_code == 401


def test_participant_cannot_enroll_403(api):
    client, TestSession = api
    from app.core.models import Participant
    with TestSession() as s:
        p = Participant(study_code="P-STAFF"); s.add(p); s.commit(); pid = p.id
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    assert client.post(ENROLL, headers=hdr).status_code == 403
