"""
tests/test_staff_onboarding.py — Convite e redefinição de senha de staff (F4.7/ADR-094).

Prova o "Pronto (DoD)":
  (1) criar sem `password` CONVIDA: a conta nasce sem senha utilizável e o link vai por e-mail;
  (2) o admin nunca vê o token (nem na resposta, nem na auditoria) — pode destravar um colega,
      não assumir a conta dele;
  (3) o link define a senha e permite login; é de USO ÚNICO e expira;
  (4) redefinir senha NÃO mexe no MFA — quem tinha 2º fator continua precisando dele;
  (5) emitir um token novo invalida o pendente;
  (6) conta desativada não recebe link (409) nem consegue consumir um emitido antes;
  (7) token inválido/expirado/consumido devolve o MESMO 401 genérico (nada de oráculo);
  (8) auditoria sem token, sem senha e sem e-mail;
  (9) o endpoint público é limitado por IP (429);
 (10) o expurgo de retenção alcança os tokens expirados.
"""
from __future__ import annotations
import datetime as dt

from sqlalchemy import select

from app.core import auth
from app.core.email import MemoryEmailSender, set_email_sender
from app.core.models import AuditLog, StaffSetupToken, StaffUser
from app.modules.retention.service import purge_expired_staff_tokens
from app.modules.staff import setup_service

STAFF = "/v1/staff"
SETUP = "/v1/staff/setup-password"
LOGIN = "/v1/auth/token"
SENHA = "Senha-Forte-123"
NOVA = "Outra-Senha-456"


def _admin(TestSession):
    with TestSession() as s:
        u = StaffUser(email="admin@uninta.edu.br", password_hash=auth.hash_password(SENHA),
                      role="admin", mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return uid, {"Authorization": f"Bearer {auth.issue_access(str(uid), 'admin')}"}


def _token_do_email(caixa: MemoryEmailSender) -> str:
    """Extrai o token do corpo do e-mail — é o único lugar onde ele existe em claro."""
    corpo = caixa.outbox[-1].body
    marca = "Token: "
    if marca in corpo:
        return corpo.split(marca, 1)[1].splitlines()[0].strip()
    return corpo.split("?token=", 1)[1].splitlines()[0].strip()


def test_criar_sem_senha_convida_e_manda_link(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    r = client.post(STAFF, headers=admin,
                    json={"email": "novo@uninta.edu.br", "role": "researcher"})
    assert r.status_code == 201 and r.json()["invited"] is True
    # O link foi para a PESSOA, não para quem convidou.
    assert len(caixa.outbox) == 1 and caixa.outbox[0].to == "novo@uninta.edu.br"
    # O token não vaza pela resposta da API.
    assert "token" not in str(r.json()).lower()


def test_conta_convidada_nao_tem_senha_utilizavel(api):
    client, TestSession = api
    set_email_sender(MemoryEmailSender())
    _uid, admin = _admin(TestSession)
    client.post(STAFF, headers=admin, json={"email": "sem@uninta.edu.br", "role": "researcher"})
    # Nenhuma senha conhecida entra — nem vazia, nem a do admin.
    for tentativa in ("", SENHA, "password"):
        r = client.post(LOGIN, json={"email": "sem@uninta.edu.br", "password": tentativa})
        assert r.status_code in (401, 422)


def test_link_define_a_senha_e_permite_login(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    client.post(STAFF, headers=admin, json={"email": "usa@uninta.edu.br", "role": "researcher"})
    token = _token_do_email(caixa)

    r = client.post(SETUP, json={"token": token, "new_password": NOVA})
    assert r.status_code == 200 and r.json() == {"status": "password_set", "mfa_enabled": False}
    assert client.post(LOGIN, json={"email": "usa@uninta.edu.br",
                                    "password": NOVA}).status_code == 200


def test_link_e_de_uso_unico(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    client.post(STAFF, headers=admin, json={"email": "uma@uninta.edu.br", "role": "researcher"})
    token = _token_do_email(caixa)
    assert client.post(SETUP, json={"token": token, "new_password": NOVA}).status_code == 200
    # Segundo uso: mesmo 401 genérico de um token que nunca existiu.
    r2 = client.post(SETUP, json={"token": token, "new_password": "Terceira-Senha-789"})
    assert r2.status_code == 401
    r3 = client.post(SETUP, json={"token": "z" * 43, "new_password": "Terceira-Senha-789"})
    assert r3.status_code == 401 and r3.json()["detail"] == r2.json()["detail"]


def test_reset_por_admin_manda_link_e_nao_revela_token(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    with TestSession() as s:
        alvo = StaffUser(email="perdeu@uninta.edu.br",
                         password_hash=auth.hash_password(SENHA), role="researcher")
        s.add(alvo); s.commit(); alvo_id = alvo.id

    r = client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "reset_email_sent"
    assert "token" not in str(r.json()).lower()
    assert caixa.outbox[-1].to == "perdeu@uninta.edu.br"     # vai para a PESSOA

    # O admin só destrava; quem define a senha é a pessoa.
    token = _token_do_email(caixa)
    assert client.post(SETUP, json={"token": token, "new_password": NOVA}).status_code == 200
    assert client.post(LOGIN, json={"email": "perdeu@uninta.edu.br",
                                    "password": NOVA}).status_code == 200


def test_redefinir_senha_nao_desliga_o_mfa(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    with TestSession() as s:
        alvo = StaffUser(email="comfa@uninta.edu.br", password_hash=auth.hash_password(SENHA),
                         role="researcher", mfa_enabled=True, mfa_secret=b"JBSWY3DPEHPK3PXP")
        s.add(alvo); s.commit(); alvo_id = alvo.id
    client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin)
    r = client.post(SETUP, json={"token": _token_do_email(caixa), "new_password": NOVA})
    # Redefinir senha não pode virar atalho para pular o 2º fator (caminho de insider).
    assert r.status_code == 200 and r.json()["mfa_enabled"] is True
    with TestSession() as s:
        assert s.get(StaffUser, alvo_id).mfa_enabled is True


def test_token_novo_invalida_o_pendente(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    with TestSession() as s:
        alvo = StaffUser(email="dois@uninta.edu.br", password_hash=auth.hash_password(SENHA),
                         role="researcher")
        s.add(alvo); s.commit(); alvo_id = alvo.id
    client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin)
    primeiro = _token_do_email(caixa)
    client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin)
    segundo = _token_do_email(caixa)
    assert primeiro != segundo
    assert client.post(SETUP, json={"token": primeiro,
                                    "new_password": NOVA}).status_code == 401
    assert client.post(SETUP, json={"token": segundo,
                                    "new_password": NOVA}).status_code == 200


def test_conta_desativada_nao_recebe_nem_consome_link(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    with TestSession() as s:
        alvo = StaffUser(email="off@uninta.edu.br", password_hash=auth.hash_password(SENHA),
                         role="researcher")
        s.add(alvo); s.commit(); alvo_id = alvo.id
    client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin)
    token = _token_do_email(caixa)
    assert client.post(f"{STAFF}/{alvo_id}/deactivate", headers=admin).status_code == 200

    # Nem novo link para conta suspensa...
    assert client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin).status_code == 409
    # ...nem o link emitido antes da suspensão vale como caminho de volta.
    assert client.post(SETUP, json={"token": token, "new_password": NOVA}).status_code == 401


def test_reset_de_staff_inexistente_404_e_researcher_403(api):
    client, TestSession = api
    _uid, admin = _admin(TestSession)
    import uuid as _uuid
    assert client.post(f"{STAFF}/{_uuid.uuid4()}/password-reset",
                       headers=admin).status_code == 404
    with TestSession() as s:
        r = StaffUser(email="pesq@uninta.edu.br", password_hash=auth.hash_password(SENHA),
                      role="researcher")
        s.add(r); s.commit(); rid = r.id
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(rid), 'researcher')}"}
    assert client.post(f"{STAFF}/{rid}/password-reset", headers=hdr).status_code == 403


def test_token_expirado_nao_serve(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    with TestSession() as s:
        alvo = StaffUser(email="velho@uninta.edu.br", password_hash=auth.hash_password(SENHA),
                         role="researcher")
        s.add(alvo); s.commit(); alvo_id = alvo.id
    client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin)
    token = _token_do_email(caixa)
    with TestSession() as s:                       # envelhece o token
        row = s.scalar(select(StaffSetupToken).where(StaffSetupToken.staff_id == alvo_id))
        row.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        s.commit()
    assert client.post(SETUP, json={"token": token, "new_password": NOVA}).status_code == 401


def test_auditoria_sem_token_sem_senha_sem_email(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    client.post(STAFF, headers=admin, json={"email": "audit@uninta.edu.br", "role": "researcher"})
    token = _token_do_email(caixa)
    client.post(SETUP, json={"token": token, "new_password": NOVA})
    with TestSession() as s:
        acoes = [a.action for a in s.scalars(select(AuditLog)).all()]
        blob = str([(a.action, a.meta) for a in s.scalars(select(AuditLog)).all()])
    assert "staff.invited" in acoes and "staff.password_set" in acoes
    assert token not in blob and NOVA not in blob and "audit@uninta.edu.br" not in blob


def test_endpoint_publico_tem_rate_limit(api, monkeypatch):
    monkeypatch.setenv("STAFF_SETUP_RATE_LIMIT", "3")
    client, _ = api
    for _ in range(3):
        assert client.post(SETUP, json={"token": "x" * 43,
                                        "new_password": NOVA}).status_code == 401
    # Endpoint público sem freio seria oráculo de força bruta de token.
    assert client.post(SETUP, json={"token": "x" * 43,
                                    "new_password": NOVA}).status_code == 429


def test_expurgo_alcanca_tokens_expirados(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    with TestSession() as s:
        alvo = StaffUser(email="purga@uninta.edu.br", password_hash=auth.hash_password(SENHA),
                         role="researcher")
        s.add(alvo); s.commit(); alvo_id = alvo.id
    client.post(f"{STAFF}/{alvo_id}/password-reset", headers=admin)
    with TestSession() as s:
        row = s.scalar(select(StaffSetupToken).where(StaffSetupToken.staff_id == alvo_id))
        row.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)
        s.commit()
        assert purge_expired_staff_tokens(s, grace_min=60) == 1
        s.commit()
        assert s.scalar(select(StaffSetupToken)) is None
        assert purge_expired_staff_tokens(s, grace_min=60) == 0      # idempotente


def test_link_do_email_respeita_query_ja_existente(api, monkeypatch):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)

    # Base sem query: entra com `?`.
    monkeypatch.setenv("STAFF_SETUP_URL", "https://app.exemplo/sereno/")
    client.post(STAFF, headers=admin, json={"email": "l1@uninta.edu.br", "role": "researcher"})
    assert "https://app.exemplo/sereno/?token=" in caixa.outbox[-1].body

    # Base que JÁ carrega query (o app web usa `?api=<túnel>/v1`): tem de entrar com `&`,
    # senão o link sai com dois `?` e o navegador não enxerga o token.
    monkeypatch.setenv("STAFF_SETUP_URL", "https://app.exemplo/sereno/?api=https://t.dev/v1")
    client.post(STAFF, headers=admin, json={"email": "l2@uninta.edu.br", "role": "researcher"})
    corpo = caixa.outbox[-1].body
    assert "?api=https://t.dev/v1&token=" in corpo
    assert corpo.count("?") == 1


def test_token_guardado_so_como_hash(api):
    client, TestSession = api
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    _uid, admin = _admin(TestSession)
    client.post(STAFF, headers=admin, json={"email": "hash@uninta.edu.br", "role": "researcher"})
    token = _token_do_email(caixa)
    with TestSession() as s:
        row = s.scalar(select(StaffSetupToken))
    # Quem lê o banco não consegue usar o link.
    assert row.token_hash != token and row.token_hash == setup_service.hash_token(token)
    assert len(row.token_hash) == 64
