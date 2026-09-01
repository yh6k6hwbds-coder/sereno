"""
modules/adverse_events/router.py — Evento adverso: relatar, LER e acompanhar até o desfecho.

POST /v1/adverse-events (participante `ae:write`): registra um evento (tipo, gravidade,
conduta), opcionalmente ligado a uma sessão SUA (IDOR → 404). Eventos moderados/graves
acionam `requires_attention` e a resposta SEMPRE reforça a orientação de procurar ajuda
profissional — coerente com "ferramenta complementar". problem+json em erros.

GET /v1/adverse-events (staff `research:read`): a lista, pseudonimizada. **Segurança é
desfecho primário e, até o ADR-110, era o único dado do estudo que ninguém conseguia ler**:
havia só o POST. A equipe recebia um e-mail dizendo "acesse o painel de pesquisa para os
detalhes" — e o painel não existia; o relato ficava no banco, alcançável só por SQL.

POST /v1/adverse-events/{id}/outcome (staff `enroll:write`): registra o desfecho. A coluna
``outcome`` existia no schema desde o ADR-051 e **nada jamais a escrevia**: um evento entrava
e nunca era fechado. Acompanhar EA até a resolução é o que o CEP espera de desfecho primário.

**Cegamento:** nada aqui devolve braço, protocolo ou PII. A lista sai por ``study_code``, que
é o mesmo pseudônimo que o restante da API da equipe usa.
"""
from __future__ import annotations
import datetime as dt
import os
import uuid
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_db
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import AdverseEvent, Participant, Session as SessionModel
from app.modules.audit.service import record_event
from app.core.email import get_email_delivery, EmailMessage

router = APIRouter(prefix="/adverse-events", tags=["adverse-events"])

_GUIDANCE = "Se os sintomas persistirem ou piorarem, procure atendimento profissional."
_GUIDANCE_URGENT = ("Procure atendimento o quanto antes. Em caso de emergência, ligue 192; "
                    "se houver sofrimento emocional, o CVV atende no 188.")


class AdverseEventIn(BaseModel):
    type: str = Field(min_length=2, max_length=40)
    severity: Literal["mild", "moderate", "severe"]
    session_id: uuid.UUID | None = None
    action: str | None = Field(default=None, max_length=200)


class AdverseEventOut(BaseModel):
    """Um evento como a EQUIPE o vê: pseudonimizado, sem braço e sem PII.

    ``requires_attention`` é recalculado da gravidade em vez de guardado: era assim que o POST
    o derivava, e duas fontes para a mesma verdade divergem no dia em que a regra mudar."""
    id: uuid.UUID
    study_code: str
    type: str
    severity: Literal["mild", "moderate", "severe"]
    action: str | None
    outcome: str | None
    requires_attention: bool
    session_id: uuid.UUID | None
    occurred_at: dt.datetime


class AdverseEventPage(BaseModel):
    items: list[AdverseEventOut]


class AdverseEventOutcomeIn(BaseModel):
    outcome: str = Field(min_length=2, max_length=200)


def notify_team(event_id: uuid.UUID, severity: str) -> None:
    """Alerta a equipe do estudo por e-mail em EA moderado/grave. Best-effort, SEM PII.

    Destino em ``TEAM_NOTIFY_EMAIL``; sem ele, não notifica. A mensagem traz só o id do
    evento e a gravidade (nada de dados do participante)."""
    to = os.getenv("TEAM_NOTIFY_EMAIL")
    if not to:
        return
    # Entrega desacoplada do request (porta `EmailDelivery`, ADR-085); nunca propaga.
    get_email_delivery().deliver(EmailMessage(
        to=to,
        subject=f"[Sereno] Evento adverso ({severity})",
        # Aponta para o endpoint que EXISTE. Até o ADR-110 esta frase mandava a equipe a um
        # "painel de pesquisa" que nunca foi construído — o aviso chegava e não havia para
        # onde ir. Sem PII e sem o texto do relato: quem tem acesso lê pela API.
        body=(f"Um evento adverso de gravidade '{severity}' foi registrado "
              f"(id {event_id}). Consulte GET /v1/adverse-events?pending=true e registre o "
              f"desfecho em POST /v1/adverse-events/{event_id}/outcome."),
    ))


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


ATTENTION_SEVERITIES = ("moderate", "severe")


def _actor_id(user: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        return None


def _to_out(ae: AdverseEvent, study_code: str) -> AdverseEventOut:
    return AdverseEventOut(
        id=ae.id, study_code=study_code, type=ae.type, severity=ae.severity,
        action=ae.action, outcome=ae.outcome,
        requires_attention=ae.severity in ATTENTION_SEVERITIES,
        session_id=ae.session_id, occurred_at=ae.occurred_at)


@router.get("", response_model=AdverseEventPage)
async def list_adverse_events(limit: int = 100, severity: str | None = None,
                              pending: bool = False,
                              db: DbSession = Depends(get_db),
                              _user: dict = Depends(require("research:read"))):
    """Os eventos adversos, do mais recente para o mais antigo.

    ``pending=true`` deixa só o que exige ação da equipe: gravidade moderada/grave **ainda sem
    desfecho registrado**. É a pergunta que a equipe de fato faz ao abrir a lista — "o que
    ainda está em aberto?" —, e sem ela a triagem seria feita a olho numa lista que só cresce.

    Ordena por ``occurred_at`` E POR ``id``: eventos relatados no mesmo instante empatariam, e
    um empate não resolvido faz a página variar entre chamadas iguais."""
    limit = max(1, min(limit, 500))
    q = (select(AdverseEvent, Participant.study_code)
         .join(Participant, Participant.id == AdverseEvent.participant_id))
    if severity is not None:
        if severity not in ("mild", "moderate", "severe"):
            raise ProblemException(422, "Gravidade inválida",
                                   "Use mild, moderate ou severe.")
        q = q.where(AdverseEvent.severity == severity)
    if pending:
        q = q.where(AdverseEvent.severity.in_(ATTENTION_SEVERITIES),
                    AdverseEvent.outcome.is_(None))
    linhas = db.execute(
        q.order_by(AdverseEvent.occurred_at.desc(), AdverseEvent.id).limit(limit)).all()
    return AdverseEventPage(items=[_to_out(ae, code) for ae, code in linhas])


@router.post("/{event_id}/outcome", response_model=AdverseEventOut)
async def record_outcome(event_id: uuid.UUID, body: AdverseEventOutcomeIn,
                         db: DbSession = Depends(get_db),
                         user: dict = Depends(require("enroll:write"))):
    """Registra o desfecho de um evento adverso — o passo que fecha o acompanhamento.

    **Sobrescrever é permitido de propósito:** um desfecho pode evoluir ("em acompanhamento" →
    "resolvido"), e obrigar a equipe a abrir um evento novo para corrigir uma frase encheria a
    lista de duplicatas justamente na tabela em que contar eventos importa. A trilha de
    auditoria guarda cada gravação, então a história não se perde."""
    ae = db.get(AdverseEvent, event_id)
    if ae is None:
        raise ProblemException(404, "Evento não encontrado", "Evento adverso inexistente.")
    ae.outcome = body.outcome
    db.flush()

    # Auditoria SEM o texto do desfecho: é dado de saúde, e a trilha é lida por mais gente
    # do que a lista. Guarda que houve o registro, por quem e sobre qual evento.
    record_event(db, action="adverse_event.outcome_recorded", resource_type="adverse_event",
                 actor_type="staff", actor_id=_actor_id(user), resource_id=ae.id,
                 meta={"severity": ae.severity})

    code = db.scalar(select(Participant.study_code).where(
        Participant.id == ae.participant_id))
    return _to_out(ae, code or "-")
