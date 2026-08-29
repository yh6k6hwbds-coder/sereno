"""
modules/staff/setup_service.py — Convite e redefinição de senha de staff (F4.7/ADR-094).

Um único mecanismo serve aos dois casos: a pessoa **define a própria senha** a partir de um
token de uso único enviado ao seu e-mail. `purpose` só distingue o texto e a auditoria.

Invariantes de segurança (as mesmas do OTP, ADR-063):
  - o token só existe em claro no e-mail; no banco fica **sha256(token+pepper)**;
  - uso único, com expiração curta; emitir um novo **invalida os anteriores** da pessoa;
  - o admin que dispara **não** recebe o token — pode destravar um colega, não assumir a conta;
  - definir senha **não mexe no MFA**: quem tinha segundo fator continua precisando dele;
  - conta desativada não recebe token (seria um caminho de volta para acesso suspenso).
"""
from __future__ import annotations
import datetime as dt
import hashlib
import os
import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.email import EmailMessage, get_email_delivery
from app.core.models import StaffSetupToken, StaffUser

# Pepper próprio: um vazamento do banco não permite testar tokens sem o segredo do cofre.
_PEPPER = os.getenv("STAFF_SETUP_PEPPER", "dev-staff-setup-pepper-trocar")

# TTLs distintos por intenção: o convite espera alguém organizar a agenda; a redefinição é
# reação a um problema em curso e deve fechar a janela rápido.
INVITE_TTL_H = 72
RESET_TTL_H = 2


def _ttl_hours(purpose: str) -> int:
    if purpose == "invite":
        return int(os.getenv("STAFF_INVITE_TTL_H", str(INVITE_TTL_H)))
    return int(os.getenv("STAFF_RESET_TTL_H", str(RESET_TTL_H)))


def hash_token(token: str) -> str:
    return hashlib.sha256((token + _PEPPER).encode("utf-8")).hexdigest()


def unusable_password_hash() -> str:
    """Hash de uma senha aleatória que ninguém conhece — conta convidada não tem senha.

    Deixar o campo vazio/nulo exigiria tratar o caso em todo verificador; um hash de valor
    desconhecido faz `verify_password` simplesmente nunca casar, sem exceção no login."""
    from app.core import auth
    return auth.hash_password(secrets.token_urlsafe(32))


def issue(db: Session, staff: StaffUser, *, purpose: str) -> tuple[str, dt.datetime]:
    """Emite um token (invalidando os pendentes da pessoa) e devolve (token, expiração).

    O token em claro volta **só para quem envia o e-mail** — nunca para a resposta HTTP."""
    db.execute(update(StaffSetupToken)
               .where(StaffSetupToken.staff_id == staff.id,
                      StaffSetupToken.consumed == False)  # noqa: E712
               .values(consumed=True))
    token = secrets.token_urlsafe(32)
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=_ttl_hours(purpose))
    db.add(StaffSetupToken(staff_id=staff.id, token_hash=hash_token(token),
                           purpose=purpose, expires_at=expires_at))
    db.flush()
    return token, expires_at


def deliver(staff: StaffUser, token: str, *, purpose: str, expires_at: dt.datetime) -> None:
    """Envia o link ao e-mail do PRÓPRIO staff. Best-effort (porta `EmailDelivery`)."""
    base = os.getenv("STAFF_SETUP_URL", "").strip().rstrip("/")
    alvo = f"{base}?token={token}" if base else f"Token: {token}"
    convite = purpose == "invite"
    assunto = ("Convite para o painel do Sereno" if convite
               else "Redefinição de senha — Sereno")
    corpo = (
        ("Você foi cadastrado(a) na equipe do estudo Sereno.\n\n"
         if convite else
         "Um administrador solicitou a redefinição da sua senha do Sereno.\n\n")
        + "Defina sua senha por este link de uso único:\n"
        + f"{alvo}\n\n"
        + f"O link expira em {expires_at.strftime('%d/%m/%Y %H:%M UTC')} e só pode ser usado "
          "uma vez.\n"
        + "Se você não esperava esta mensagem, ignore-a e avise a coordenação do estudo.\n"
        + "Definir a senha NÃO altera seu segundo fator (MFA)."
    )
    get_email_delivery().deliver(EmailMessage(to=staff.email, subject=assunto, body=corpo))


def consume(db: Session, token: str) -> StaffUser | None:
    """Valida e queima o token; devolve o staff dono, ou ``None`` se não serve.

    ``None`` cobre inexistente, expirado, já consumido e conta desativada — o chamador
    responde 401 genérico para os quatro, para não virar oráculo de existência."""
    row = db.scalar(select(StaffSetupToken)
                    .where(StaffSetupToken.token_hash == hash_token(token),
                           StaffSetupToken.consumed == False))  # noqa: E712
    if row is None:
        return None
    expires_at = row.expires_at
    if expires_at.tzinfo is None:                 # SQLite devolve naive; Postgres, aware
        expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
    if expires_at <= dt.datetime.now(dt.timezone.utc):
        return None
    staff = db.get(StaffUser, row.staff_id)
    if staff is None or not staff.is_active:
        return None
    row.consumed = True                           # uso único: queima antes de devolver
    db.flush()
    return staff


def staff_by_id(db: Session, staff_id: str) -> StaffUser | None:
    try:
        return db.get(StaffUser, uuid.UUID(str(staff_id)))
    except (ValueError, TypeError):
        return None
