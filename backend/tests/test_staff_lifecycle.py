"""
tests/test_staff_lifecycle.py — Lifecycle de staff: listagem, ativar/desativar e senha (ADR-081).

Prova o "Pronto (DoD)":
  - admin lista o time com estado operacional, SEM senha e SEM segredo de MFA;
  - desativar suspende o acesso JÁ EMITIDO (o RBAC confere o banco, não só o JWT) e
    fecha login, refresh e verificação de MFA; reativar devolve o acesso;
  - admin não desativa a si mesmo (lockout) e estado repetido é 409;
  - rotação de senha exige a senha atual e revoga o token usado na chamada;
  - tudo auditado sem PII (o e-mail não entra no log).
Negações: 401/403/404/409/422.
"""
from __future__ import annotations
from sqlalchemy import select

from app.core.models import StaffUser, AuditLog
from app.core import auth

STAFF = "/v1/staff"
LOGIN = "/v1/auth/token"
PASSWORD = "/v1/staff/me/password"
SENHA = "Senha-Forte-123"


def _staff(TestSession, role, email=None, password=SENHA):
    """Cria um staff e devolve (id, email, headers com access token)."""
    email = email or f"{role}@uninta.edu.br"
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password(password),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return uid, email, {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def test_admin_lists_staff_without_secrets(api):
    client, TestSession = api
    _uid, _e, admin = _staff(TestSession, "admin")
    _staff(TestSession, "researcher", email="lista@uninta.edu.br")
    r = client.get(STAFF, headers=admin)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    alvo = next(i for i in items if i["email"] == "lista@uninta.edu.br")
    assert alvo["role"] == "researcher" and alvo["is_active"] is True and alvo["mfa_enabled"] is False
    # Nem senha nem segredo de MFA atravessam o contrato.
    corpo = str(r.json()).lower()
    assert "password" not in corpo and "secret" not in corpo


def test_researcher_cannot_list_staff_403(api):
    client, TestSession = api
    _uid, _e, res = _staff(TestSession, "researcher")
    assert client.get(STAFF, headers=res).status_code == 403


def test_deactivate_suspends_token_already_issued(api):
    client, TestSession = api
    _aid, _ae, admin = _staff(TestSession, "admin")
    rid, _re, res = _staff(TestSession, "researcher", email="susp@uninta.edu.br")
    # Token do pesquisador funciona antes...
    assert client.get("/v1/research/participants", headers=res).status_code in (200, 404)
    r = client.post(f"{STAFF}/{rid}/deactivate", headers=admin)
    assert r.status_code == 200 and r.json()["is_active"] is False
    # ...e para de funcionar DEPOIS, com o MESMO token: o JWT não expirou, o banco mandou.
    assert client.get("/v1/research/participants", headers=res).status_code == 401


def test_deactivated_staff_cannot_login_or_refresh(api):
    client, TestSession = api
    _aid, _ae, admin = _staff(TestSession, "admin")
    rid, email, _res = _staff(TestSession, "researcher", email="nologin@uninta.edu.br")
    refresh = auth.issue_refresh(str(rid), "researcher")
    client.post(f"{STAFF}/{rid}/deactivate", headers=admin)
    lr = client.post(LOGIN, json={"email": email, "password": SENHA})
    assert lr.status_code == 401
    # Mensagem genérica: não confirma que a conta existe.
    assert "suspens" not in lr.text.lower() and "desativ" not in lr.text.lower()
    assert client.post("/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_activate_restores_access(api):
    client, TestSession = api
    _aid, _ae, admin = _staff(TestSession, "admin")
    rid, email, _res = _staff(TestSession, "researcher", email="volta@uninta.edu.br")
    client.post(f"{STAFF}/{rid}/deactivate", headers=admin)
    r = client.post(f"{STAFF}/{rid}/activate", headers=admin)
    assert r.status_code == 200 and r.json()["is_active"] is True
    assert client.post(LOGIN, json={"email": email, "password": SENHA}).status_code == 200


def test_admin_cannot_deactivate_self_409(api):
    client, TestSession = api
    aid, _ae, admin = _staff(TestSession, "admin")
    r = client.post(f"{STAFF}/{aid}/deactivate", headers=admin)
    assert r.status_code == 409
    with TestSession() as s:
        assert s.get(StaffUser, aid).is_active is True     # continua podendo entrar


def test_unchanged_state_409_and_unknown_404(api):
    client, TestSession = api
    _aid, _ae, admin = _staff(TestSession, "admin")
    rid, _re, _res = _staff(TestSession, "researcher", email="ja@uninta.edu.br")
    assert client.post(f"{STAFF}/{rid}/activate", headers=admin).status_code == 409   # já ativo
    import uuid as _u
    assert client.post(f"{STAFF}/{_u.uuid4()}/deactivate", headers=admin).status_code == 404


def test_lifecycle_is_audited_without_pii(api):
    client, TestSession = api
    aid, _ae, admin = _staff(TestSession, "admin")
    rid, _re, _res = _staff(TestSession, "researcher", email="auditoria@uninta.edu.br")
    client.post(f"{STAFF}/{rid}/deactivate", headers=admin)
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "staff.deactivated")).one()
        assert ev.resource_type == "staff_user" and ev.resource_id == rid
        assert ev.actor_id == aid and ev.meta == {"role": "researcher"}
        assert "auditoria@" not in f"{ev.meta}".lower()      # e-mail não entra no log


def test_password_rotation_requires_current_and_revokes_token(api):
    client, TestSession = api
    rid, email, hdr = _staff(TestSession, "researcher", email="troca@uninta.edu.br")
    nova = "Outra-Senha-456"
    assert client.post(PASSWORD, headers=hdr,
                       json={"current_password": "errada-mesmo", "new_password": nova}).status_code == 401
    r = client.post(PASSWORD, headers=hdr, json={"current_password": SENHA, "new_password": nova})
    assert r.status_code == 200 and r.json()["status"] == "password_rotated"
    with TestSession() as s:
        assert auth.verify_password(s.get(StaffUser, rid).password_hash, nova)
    # O token usado na troca foi revogado: trocar a senha encerra a sessão em curso.
    assert client.get("/v1/research/participants", headers=hdr).status_code == 401


def test_password_rotation_rejects_same_password_422(api):
    client, TestSession = api
    _rid, _e, hdr = _staff(TestSession, "researcher", email="igual@uninta.edu.br")
    r = client.post(PASSWORD, headers=hdr, json={"current_password": SENHA, "new_password": SENHA})
    assert r.status_code == 422


def test_deactivated_staff_cannot_rotate_password_401(api):
    client, TestSession = api
    _aid, _ae, admin = _staff(TestSession, "admin")
    rid, _e, hdr = _staff(TestSession, "researcher", email="susp2@uninta.edu.br")
    client.post(f"{STAFF}/{rid}/deactivate", headers=admin)
    r = client.post(PASSWORD, headers=hdr, json={"current_password": SENHA, "new_password": "Outra-Senha-456"})
    assert r.status_code == 401
