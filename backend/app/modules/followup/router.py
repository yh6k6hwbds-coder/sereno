"""
modules/followup/router.py — Seguimento (fim do estudo).

POST /v1/participants/me/followup: reusa o motor de escore validado (PSQI, GAD-7) e
acrescenta SUS (usabilidade) e o ITEM DE INTEGRIDADE DO CEGAMENTO (o palpite do
participante sobre seu braço). Persiste BRUTO + escore VERSIONADO (reprodutibilidade),
igual à linha de base. Um seguimento por participante (409).

Metodologia: `blinding_guess` é apenas o que o participante ACHA — NUNCA é comparado
nem substituído pelo braço real aqui; o cegamento permanece intacto. Esse dado alimenta
o índice de Bang (Etapa 7).
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
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import FollowupAssessment
from app.modules.instruments.router import PSQIIn, Score03
from app.modules.instruments.instruments_scoring import score_gad7, score_psqi, score_sus, PSQIInput

router = APIRouter(prefix="/participants/me", tags=["followup"])

Score15 = Annotated[int, Field(ge=1, le=5)]     # item SUS 1–5


class FollowupIn(BaseModel):
    gad7_items: conlist(Score03, min_length=7, max_length=7)
    psqi: PSQIIn
    sus_items: conlist(Score15, min_length=10, max_length=10)
    blinding_guess: Literal["A", "B", "nao_sei"]   # palpite do participante


class FollowupOut(BaseModel):
    gad7_total: int
    gad7_severity: str
    psqi_global: int
    psqi_interpretation: str
    sus_score: float
    sus_band: str
    blinding_guess: str
    score_version: str


@router.get("/followup/_status")
async def status():
    return {"module": "followup"}


@router.post("/followup", status_code=201, response_model=FollowupOut)
async def submit_followup(body: FollowupIn, db: Session = Depends(get_db),
                          participant_id: uuid.UUID = Depends(current_participant),
                          _user: dict = Depends(require("assessment:write"))):
    if db.scalar(select(FollowupAssessment.id).where(FollowupAssessment.participant_id == participant_id)) is not None:
        raise ProblemException(409, "Seguimento já registrado",
                               "Este participante já possui avaliação de seguimento.")
    if body.psqi.hours_slept > body.psqi.hours_in_bed:
        raise ProblemException(422, "Dados inconsistentes",
                               "hours_slept não pode exceder hours_in_bed.")

    gad7 = score_gad7(list(body.gad7_items))
    psqi = score_psqi(PSQIInput(
        subjective_quality=body.psqi.subjective_quality, latency_min=body.psqi.latency_min,
        cannot_sleep_30min_freq=body.psqi.cannot_sleep_30min_freq, hours_slept=body.psqi.hours_slept,
        hours_in_bed=body.psqi.hours_in_bed, disturbance_items=list(body.psqi.disturbance_items),
        medication_freq=body.psqi.medication_freq, stay_awake_freq=body.psqi.stay_awake_freq,
        enthusiasm_problem=body.psqi.enthusiasm_problem))
    sus = score_sus(list(body.sus_items))
    score_version = f"gad7:{gad7['version']}|psqi:{psqi['version']}|sus:{sus['version']}"

    record = FollowupAssessment(
        participant_id=participant_id,
        gad7_items=list(body.gad7_items), gad7_total=gad7["total"],
        psqi_input=body.psqi.model_dump(), psqi_global=psqi["global"],
        sus_items=list(body.sus_items), sus_score=sus["score"],
        blinding_guess=body.blinding_guess,      # apenas o palpite; nunca o braço real
        score_version=score_version, assessed_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(record)
    db.flush()

    return FollowupOut(
        gad7_total=gad7["total"], gad7_severity=gad7["severity"],
        psqi_global=psqi["global"], psqi_interpretation=psqi["interpretation"],
        sus_score=sus["score"], sus_band=sus["band"],
        blinding_guess=body.blinding_guess, score_version=score_version)
