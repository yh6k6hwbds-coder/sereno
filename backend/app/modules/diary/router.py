"""
modules/diary/router.py — Diário de sono (um registro por participante por dia).
Autenticado (participante) + RBAC (diary:write). Duplicata no mesmo dia → 409. problem+json.
"""
from __future__ import annotations
import datetime as dt
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import SleepDiary

router = APIRouter(prefix="/diary", tags=["diary"])


class DiaryIn(BaseModel):
    diary_date: dt.date
    latency_min: int | None = Field(default=None, ge=0, le=1440)
    awakenings: int | None = Field(default=None, ge=0, le=50)
    duration_h: float | None = Field(default=None, ge=0, le=24)
    quality: int | None = Field(default=None, ge=0, le=4)


@router.post("", status_code=201)
async def add_entry(body: DiaryIn, db: Session = Depends(get_db),
                    participant_id: uuid.UUID = Depends(current_participant),
                    _user: dict = Depends(require("diary:write"))):
    dup = db.scalar(select(SleepDiary.id).where(
        SleepDiary.participant_id == participant_id, SleepDiary.diary_date == body.diary_date))
    if dup is not None:
        raise ProblemException(409, "Diário já registrado", "Já existe registro para esta data.")
    db.add(SleepDiary(participant_id=participant_id, diary_date=body.diary_date,
                      latency_min=body.latency_min, awakenings=body.awakenings,
                      duration_h=body.duration_h, quality=body.quality))
    db.flush()
    return {"status": "recorded", "diary_date": body.diary_date.isoformat()}
