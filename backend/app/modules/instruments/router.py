"""
modules/instruments/router.py — Linha de base (PSQI + GAD-7). Fatia científica.

POST /v1/participants/me/baseline: recebe as respostas, pontua NO SERVIDOR reusando
o módulo validado (instruments_scoring.py), e persiste RESPOSTAS BRUTAS + escore
VERSIONADO em baseline_assessment. Persistir o bruto permite recalcular se o
algoritmo evoluir (reprodutibilidade). Só a lógica de escore vive no backend; o
texto verbatim dos instrumentos não é reproduzido. Erros em problem+json.
"""
from __future__ import annotations
import datetime as dt
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, conlist
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import BaselineAssessment
from app.modules.instruments.instruments_scoring import score_gad7, score_psqi, PSQIInput

router = APIRouter(prefix="/participants/me", tags=["instruments"])

Score03 = Annotated[int, Field(ge=0, le=3)]   # item Likert 0–3 (PSQI/GAD-7)


class PSQIIn(BaseModel):
    subjective_quality: Score03                       # Q9
    latency_min: int = Field(ge=0, le=1440)           # Q2 (minutos)
    cannot_sleep_30min_freq: Score03                  # Q5a
    hours_slept: float = Field(gt=0, le=24)           # Q4
    hours_in_bed: float = Field(gt=0, le=24)          # derivado no cliente (deitar→levantar)
    disturbance_items: conlist(Score03, min_length=9, max_length=9)   # Q5b–Q5j
    medication_freq: Score03                          # Q6
    stay_awake_freq: Score03                          # Q7
    enthusiasm_problem: Score03                       # Q8


class BaselineIn(BaseModel):
    gad7_items: conlist(Score03, min_length=7, max_length=7)
    psqi: PSQIIn


class ScoreOut(BaseModel):
    gad7_total: int
    gad7_severity: str
    psqi_global: int
    psqi_interpretation: str
    score_version: str


@router.get("/baseline/_status")
async def status():
    return {"module": "instruments", "endpoint": "baseline"}


@router.post("/baseline", status_code=201, response_model=ScoreOut)
async def submit_baseline(
    body: BaselineIn,
    db: Session = Depends(get_db),
    participant_id: uuid.UUID = Depends(current_participant),
    _user: dict = Depends(require("assessment:write")),
):
    # Uma linha de base por participante (evita duplicidade).
    existing = db.scalar(select(BaselineAssessment.id).where(BaselineAssessment.participant_id == participant_id))
    if existing is not None:
        raise ProblemException(409, "Linha de base já registrada",
                               "Este participante já possui avaliação de linha de base.")

    # Validação de domínio: não se dorme mais do que se fica na cama.
    if body.psqi.hours_slept > body.psqi.hours_in_bed:
        raise ProblemException(422, "Dados inconsistentes",
                               "hours_slept não pode exceder hours_in_bed.")

    gad7 = score_gad7(list(body.gad7_items))          # módulo validado (Etapa 4)
    psqi = score_psqi(PSQIInput(
        subjective_quality=body.psqi.subjective_quality,
        latency_min=body.psqi.latency_min,
        cannot_sleep_30min_freq=body.psqi.cannot_sleep_30min_freq,
        hours_slept=body.psqi.hours_slept,
        hours_in_bed=body.psqi.hours_in_bed,
        disturbance_items=list(body.psqi.disturbance_items),
        medication_freq=body.psqi.medication_freq,
        stay_awake_freq=body.psqi.stay_awake_freq,
        enthusiasm_problem=body.psqi.enthusiasm_problem,
    ))
    score_version = f"gad7:{gad7['version']}|psqi:{psqi['version']}"

    record = BaselineAssessment(
        participant_id=participant_id,
        gad7_items=list(body.gad7_items),             # bruto (JSON)
        gad7_total=gad7["total"],
        psqi_input=body.psqi.model_dump(),            # bruto (JSON) — permite recomputar
        psqi_global=psqi["global"],
        score_version=score_version,
        assessed_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(record)
    db.flush()

    return ScoreOut(gad7_total=gad7["total"], gad7_severity=gad7["severity"],
                    psqi_global=psqi["global"], psqi_interpretation=psqi["interpretation"],
                    score_version=score_version)
