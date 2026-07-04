"""
modules/adverse_events/router.py — Relato de evento adverso (segurança é desfecho primário).

POST /v1/adverse-events: o participante registra um evento (tipo, gravidade, conduta),
opcionalmente ligado a uma sessão SUA (IDOR → 404). Eventos moderados/graves acionam
`requires_attention` (gancho de notificação da equipe) e a resposta SEMPRE reforça a
orientação de procurar ajuda profissional — coerente com "ferramenta complementar".
problem+json em erros.
"""
from __future__ import annotations
import datetime as dt
import uuid
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_db
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import AdverseEvent, Session as SessionModel

router = APIRouter(prefix="/adverse-events", tags=["adverse-events"])

_GUIDANCE = "Se os sintomas persistirem ou piorarem, procure atendimento profissional."
_GUIDANCE_URGENT = ("Procure atendimento o quanto antes. Em caso de emergência, ligue 192; "
                    "se houver sofrimento emocional, o CVV atende no 188.")


class AdverseEventIn(BaseModel):
    type: str = Field(min_length=2, max_length=40)
    severity: Literal["mild", "moderate", "severe"]
    session_id: uuid.UUID | None = None
    action: str | None = Field(default=None, max_length=200)


def notify_team(event_id: uuid.UUID, severity: str) -> None:
    """DEV: apenas registra. PROD: alertar a equipe do estudo (integração pendente)."""
    print(f"[adverse-event] ATENÇÃO ({severity}) evento {event_id}")


@router.post("", status_code=201)
async def report_adverse_event(body: AdverseEventIn, db: DbSession = Depends(get_db),
                               participant_id: uuid.UUID = Depends(current_participant),
                               _user: dict = Depends(require("ae:write"))):
    # Se ligado a uma sessão, ela precisa ser do próprio participante.
    if body.session_id is not None:
        owns = db.scalar(select(SessionModel.id).where(
            SessionModel.id == body.session_id, SessionModel.participant_id == participant_id))
        if owns is None:
            raise ProblemException(404, "Sessão não encontrada", "Sessão inexistente para este participante.")

    event = AdverseEvent(
        participant_id=participant_id, session_id=body.session_id,
        type=body.type, severity=body.severity, action=body.action,
        occurred_at=dt.datetime.now(dt.timezone.utc),
    )
    db.add(event)
    db.flush()

    requires_attention = body.severity in ("moderate", "severe")
    if requires_attention:
        notify_team(event.id, body.severity)

    return {
        "status": "recorded",
        "requires_attention": requires_attention,
        "guidance": _GUIDANCE_URGENT if body.severity == "severe" else _GUIDANCE,
    }
