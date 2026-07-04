"""
modules/participant_auth/router.py — Login de participante por e-mail + OTP (sem senha).

Decisão: participantes de pesquisa não usam senha (fricção e risco). Provam posse do
e-mail com um código de uso único, e recebem um JWT de participante. O código é gravado
apenas como hash, expira, é de uso único e tem limite de tentativas. Sem enumeração:
solicitar OTP responde de forma genérica. Entrega por e-mail é integração à parte (PROD).
"""
from __future__ import annotations
import datetime as dt
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.problem import ProblemException
from app.core.models import Participant, OtpChallenge
from app.core import otp, auth

router = APIRouter(prefix="/auth/participant", tags=["participant-auth"])


class RequestOtpIn(BaseModel):
    study_code: str


class VerifyOtpIn(BaseModel):
    study_code: str
    code: str = Field(pattern=r"^\d{6}$")


def deliver_otp(participant_id, code: str) -> None:
    """DEV: apenas registra. PROD: enviar por e-mail ao contato cifrado (integração pendente)."""
    print(f"[otp] participante {participant_id} -> código {code}")


@router.post("/request-otp")
async def request_otp(body: RequestOtpIn, db: Session = Depends(get_db)):
    p = db.scalar(select(Participant).where(Participant.study_code == body.study_code))
    if p is not None:
        # invalida desafios anteriores não consumidos e emite um novo
        db.execute(update(OtpChallenge)
                   .where(OtpChallenge.participant_id == p.id, OtpChallenge.consumed == False)  # noqa: E712
                   .values(consumed=True))
        code = otp.generate_code()
        db.add(OtpChallenge(participant_id=p.id, code_hash=otp.hash_code(code), expires_at=otp.expiry()))
        db.flush()
        deliver_otp(p.id, code)
    # Resposta genérica — não revela se o código de estudo existe.
    return {"status": "otp_sent_if_exists"}


@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpIn, db: Session = Depends(get_db)):
    generic = ProblemException(401, "Código inválido", "Código incorreto ou expirado.")
    p = db.scalar(select(Participant).where(Participant.study_code == body.study_code))
    if p is None:
        raise generic
    ch = db.scalars(select(OtpChallenge)
                    .where(OtpChallenge.participant_id == p.id, OtpChallenge.consumed == False)  # noqa: E712
                    .order_by(OtpChallenge.created_at.desc())).first()
    now = dt.datetime.now(dt.timezone.utc)
    if ch is None or otp.as_utc(ch.expires_at) < now or ch.attempts >= otp.OTP_MAX_ATTEMPTS:
        raise generic
    if not otp.verify_code(body.code, ch.code_hash):
        ch.attempts += 1
        db.commit()          # persiste a tentativa mesmo com erro (defesa contra brute force)
        raise generic
    ch.consumed = True
    db.flush()
    return {
        "access_token": auth.issue_access(str(p.id), "participant"),
        "refresh_token": auth.issue_refresh(str(p.id), "participant"),
        "token_type": "bearer",
        "expires_in": auth.ACCESS_TTL_MIN * 60,
    }
