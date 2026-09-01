"""
modules/progress/router.py — Andamento do participante e descontinuação de protocolo (G6).

GET /v1/participants/me/status (participante `progress:read`): em que semana está, quantas
sessões contaram para a adesão, se a avaliação intermediária (T2) está aberta e se houve
descontinuação. É o que permite ao aplicativo convidar para o T2 **na hora certa** em vez de
deixar a tela sempre disponível e torcer. Traz junto a **dose de exposição auditiva** (G9),
que o protocolo manda contabilizar e alertar em 50% da referência OMS/UIT. **Não** revela
braço, condição nem escore — a dose é idêntica em desenho nos dois braços (mesma energia).

POST /v1/participants/{id}/discontinue (staff `enroll:write`): registra os dois motivos que
são juízo humano — pedido do participante e evento adverso que contraindique a continuidade.
POST /v1/discontinuations/evaluate (staff `enroll:write`): aplica a regra de adesão da 2ª
semana a todos os participantes ativos — o varredor que alcança quem parou de abrir o app.
GET /v1/discontinuations (staff `research:read`): as saídas, pseudonimizadas, para o relatório
parcial ao CEP. problem+json.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import AdverseEvent, Participant, ProtocolDiscontinuation
from app.core.problem import ProblemException
from app.core.security import current_participant, require
from app.modules.progress import service as progress

router = APIRouter(tags=["progress"])


class T2Out(BaseModel):
    opens_at: dt.datetime
    closes_at: dt.datetime
    due: bool
    late: bool
    completed: bool


class HearingOut(BaseModel):
    """Dose de exposição auditiva (G9). ``calibrated=False`` = previsão, não medida."""
    calibrated: bool
    assumed_spl_dba: float | None
    reference_spl_dba: float
    reference_hours_per_week: float
    window_days: int
    week_hours: float
    week_pct: float
    total_hours: float
    total_pct: float
    alert_at_pct: float
    alert: bool


class DiscontinuationBrief(BaseModel):
    reason: str
    decided_at: dt.datetime
    kept_in_itt: bool


class ProgressOut(BaseModel):
    status: str
    allocated: bool
    study_day: int | None
    study_week: int | None
    sessions_completed: int
    sessions_prescribed: int
    adherence_pct: float
    t2: T2Out | None
    discontinuation: DiscontinuationBrief | None
    hearing: HearingOut


class DiscontinueIn(BaseModel):
    # Só os motivos de juízo humano: 'adesao_insuficiente' é regra, e a regra é de quem a aplica.
    reason: Literal["solicitacao_participante", "evento_adverso"]
    adverse_event_id: uuid.UUID | None = None


class DiscontinuationOut(BaseModel):
    id: uuid.UUID
    study_code: str
    reason: str
    study_week: int | None
    sessions_completed: int | None
    sessions_prescribed: int | None
    kept_in_itt: bool
    decided_at: dt.datetime


class DiscontinuationPage(BaseModel):
    items: list[DiscontinuationOut]


class SweepOut(BaseModel):
    evaluated_at: dt.datetime
    discontinued: int


def _actor_id(user: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        return None


@router.get("/participants/me/status", response_model=ProgressOut)
async def my_status(db: Session = Depends(get_db),
                    participant_id: uuid.UUID = Depends(current_participant),
                    _user: dict = Depends(require("progress:read"))):
    return ProgressOut(**progress.participant_progress(db, participant_id))


@router.post("/participants/{participant_id}/discontinue", status_code=201,
             response_model=DiscontinuationOut)
async def discontinue_participant(participant_id: uuid.UUID, body: DiscontinueIn,
                                  db: Session = Depends(get_db),
                                  user: dict = Depends(require("enroll:write"))):
    p = db.get(Participant, participant_id)
    if p is None:
        raise ProblemException(404, "Participante não encontrado", "ID de participante inexistente.")
    if body.reason == "evento_adverso" and body.adverse_event_id is not None:
        ae = db.get(AdverseEvent, body.adverse_event_id)
        if ae is None or ae.participant_id != participant_id:
            raise ProblemException(422, "Evento adverso inválido",
                                   "O evento informado não pertence a este participante.")
    ja = db.scalar(select(ProtocolDiscontinuation).where(
        ProtocolDiscontinuation.participant_id == participant_id))
    if ja is not None:
        raise ProblemException(409, "Já descontinuado",
                               "Este participante já possui descontinuação registrada.")

    registro = progress.discontinue(
        db, participant_id, body.reason, decided_by=_actor_id(user),
        adverse_event_id=body.adverse_event_id)
    return _to_out(registro, p.study_code)


@router.post("/discontinuations/evaluate", response_model=SweepOut)
async def evaluate_discontinuations(db: Session = Depends(get_db),
                                    _user: dict = Depends(require("enroll:write"))):
    """Aplica a regra de adesão da 2ª semana a quem está ativo (idempotente)."""
    agora = dt.datetime.now(dt.timezone.utc)
    saidas = progress.sweep_week2(db, agora)
    return SweepOut(evaluated_at=agora, discontinued=len(saidas))


@router.get("/discontinuations", response_model=DiscontinuationPage)
async def list_discontinuations(limit: int = 100, db: Session = Depends(get_db),
                                _user: dict = Depends(require("research:read"))):
    limit = max(1, min(limit, 500))
    linhas = db.execute(
        select(ProtocolDiscontinuation, Participant.study_code)
        .join(Participant, Participant.id == ProtocolDiscontinuation.participant_id)
        .order_by(ProtocolDiscontinuation.decided_at.desc())
        .limit(limit)).all()
    return DiscontinuationPage(items=[_to_out(d, code) for d, code in linhas])


def _to_out(d: ProtocolDiscontinuation, study_code: str) -> DiscontinuationOut:
    return DiscontinuationOut(
        id=d.id, study_code=study_code, reason=d.reason, study_week=d.study_week,
        sessions_completed=d.sessions_completed, sessions_prescribed=d.sessions_prescribed,
        kept_in_itt=bool(d.kept_in_itt), decided_at=d.decided_at)
