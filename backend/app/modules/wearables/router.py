"""
modules/wearables/router.py — Ingestão de vestíveis (E2/ADR-084).

POST /v1/wearables/readings (participante, `wearable:write`): recebe um lote de leituras de
FC/sono **já normalizadas** no device e as encaminha ao `WearableSink` desacoplado. No padrão
(NullSink) **nada é persistido** — é o seam preparado, não a integração construída. Responde
**202** (recebido) com a contagem aceita. Auditado sem valores (só a contagem).

**Inegociáveis:** as leituras **não alimentam o recomendador ao vivo** (segue por regras,
inegociável #5); nenhum valor de saúde entra em log (inegociável #6). problem+json em erros.
"""
from __future__ import annotations
import datetime as dt
import uuid
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require, current_participant
from app.modules.audit.service import record_event
from app.modules.wearables.sink import Reading, get_wearable_sink

router = APIRouter(prefix="/wearables", tags=["wearables"])


class ReadingIn(BaseModel):
    kind: Literal["heart_rate", "sleep"]
    taken_at: dt.datetime
    value: float = Field(ge=0, le=100000)
    unit: str = Field(min_length=1, max_length=16)
    source: str = Field(min_length=1, max_length=32, description="rótulo do provedor (healthkit/googlefit/manual)")


class ReadingsIn(BaseModel):
    readings: list[ReadingIn] = Field(min_length=1, max_length=500)


@router.post("/readings", status_code=202)
async def ingest_readings(body: ReadingsIn, db: Session = Depends(get_db),
                          participant_id: uuid.UUID = Depends(current_participant),
                          _user: dict = Depends(require("wearable:write"))):
    readings = [Reading(kind=r.kind, taken_at=r.taken_at, value=r.value, unit=r.unit, source=r.source)
                for r in body.readings]
    accepted = get_wearable_sink().ingest(participant_id, readings)
    # Auditoria SEM valores de saúde: só a contagem (o valor/horário não entram no log).
    record_event(db, action="wearable.ingested", resource_type="wearable_reading",
                 actor_type="participant", actor_id=participant_id, resource_id=participant_id,
                 meta={"accepted": accepted})
    return {"accepted": accepted}
