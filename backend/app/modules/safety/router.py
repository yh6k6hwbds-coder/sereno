"""
modules/safety/router.py — Avaliação de segurança (PHQ-9) e fichas de encaminhamento (G5).

POST /v1/participants/me/safety-check (participante `assessment:write`): PHQ-9 — e, se quiser,
GAD-7 — aplicados **por segurança**, não como desfecho. Item 9 positivo ou GAD-7 >= 15 abre a
ficha de encaminhamento, retira do protocolo e devolve orientação de cuidado.

GET /v1/referrals (staff `research:read`): as fichas, pseudonimizadas, para o relatório parcial
ao CEP. POST /v1/referrals/{id}/record (staff `enroll:write`): registra a que serviço se
encaminhou e a confirmação de acolhimento — os dois passos que o protocolo exige por escrito.

**A resposta ao participante não traz escore.** Um número de gravidade na tela, sem profissional
junto, é lido como diagnóstico; e o app é ferramenta complementar. O escore fica com a equipe.
Nada aqui revela ou depende do braço.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, conlist
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Participant, Referral
from app.core.problem import ProblemException
from app.core.security import require, current_participant
from app.modules.audit.service import record_event
from app.modules.instruments.instruments_scoring import score_gad7, score_phq9
from app.modules.safety import service as safety

router = APIRouter(tags=["safety"])

Score03 = Annotated[int, Field(ge=0, le=3)]


class SafetyCheckIn(BaseModel):
    phq9_items: conlist(Score03, min_length=9, max_length=9)
    gad7_items: conlist(Score03, min_length=7, max_length=7) | None = None
    moment: Literal["intermediaria", "espontanea"] = "intermediaria"


class SafetyCheckOut(BaseModel):
    status: str
    referral_opened: bool
    guidance: str


class ReferralOut(BaseModel):
    id: uuid.UUID
    study_code: str
    reasons: list[str]
    status: str
    service: str | None
    created_at: dt.datetime
    referred_at: dt.datetime | None
    acknowledged_at: dt.datetime | None


class ReferralPage(BaseModel):
    items: list[ReferralOut]


class ReferralRecordIn(BaseModel):
    service: Literal["apoio_institucional", "caps", "urgencia", "outro"]
    acknowledged: bool = False


def _actor_id(user: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        return None


@router.post("/participants/me/safety-check", status_code=201, response_model=SafetyCheckOut)
async def submit_safety_check(body: SafetyCheckIn, db: Session = Depends(get_db),
                              participant_id: uuid.UUID = Depends(current_participant),
                              _user: dict = Depends(require("assessment:write"))):
    phq9 = score_phq9(list(body.phq9_items))
    gad7_total = score_gad7(list(body.gad7_items))["total"] if body.gad7_items else None

    _, ficha = safety.record_assessment(
        db, participant_id, moment=body.moment, phq9=phq9, gad7_total=gad7_total,
        actor_type="participant", actor_id=participant_id)

    # A orientação vai SEMPRE, com ou sem gatilho: quem respondeu a um questionário sobre
    # sofrimento não deveria terminar a tela sem saber a quem recorrer.
    return SafetyCheckOut(status="recorded", referral_opened=ficha is not None,
                          guidance=safety.GUIDANCE)


@router.get("/referrals", response_model=ReferralPage)
async def list_referrals(limit: int = 100, db: Session = Depends(get_db),
                         _user: dict = Depends(require("research:read"))):
    limit = max(1, min(limit, 500))
    rows = db.execute(
        select(Referral, Participant.study_code)
        .join(Participant, Participant.id == Referral.participant_id)
        .order_by(Referral.created_at.desc())
        .limit(limit)).all()
    return ReferralPage(items=[
        ReferralOut(id=r.id, study_code=code, reasons=list(r.reasons or []), status=r.status,
                    service=r.service, created_at=r.created_at, referred_at=r.referred_at,
                    acknowledged_at=r.acknowledged_at)
        for r, code in rows])


@router.post("/referrals/{referral_id}/record", response_model=ReferralOut)
async def record_referral(referral_id: uuid.UUID, body: ReferralRecordIn,
                          db: Session = Depends(get_db),
                          user: dict = Depends(require("enroll:write"))):
    ficha = db.get(Referral, referral_id)
    if ficha is None:
        raise ProblemException(404, "Ficha não encontrada", "Encaminhamento inexistente.")

    agora = dt.datetime.now(dt.timezone.utc)
    ficha.service = body.service
    if ficha.referred_at is None:
        ficha.referred_at = agora
    if body.acknowledged and ficha.acknowledged_at is None:
        ficha.acknowledged_at = agora
    ficha.status = "acolhido" if ficha.acknowledged_at is not None else "encaminhado"
    db.flush()

    record_event(db, action="referral.recorded", resource_type="referral",
                 actor_type="staff", actor_id=_actor_id(user), resource_id=ficha.id,
                 meta={"service": ficha.service, "status": ficha.status})

    code = db.scalar(select(Participant.study_code).where(Participant.id == ficha.participant_id))
    return ReferralOut(id=ficha.id, study_code=code or "-", reasons=list(ficha.reasons or []),
                       status=ficha.status, service=ficha.service, created_at=ficha.created_at,
                       referred_at=ficha.referred_at, acknowledged_at=ficha.acknowledged_at)
