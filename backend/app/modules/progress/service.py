"""
modules/progress/service.py — Onde o participante está no protocolo, e quando ele sai (G6).

Duas coisas que o protocolo pede e o sistema não tinha:

  1. **A avaliação intermediária T2.** O instrumento (PHQ-9 de segurança) e a tela já existem
     desde o G5; o que faltava era o **momento** — quando ela é devida, até quando, e se já foi
     respondida. Sem isso, "coleta em T0, T2 e T4" era um parágrafo do protocolo sem
     contrapartida no software: nada convidava o participante na 2ª semana.
  2. **A descontinuação de protocolo.** O protocolo lista três critérios — pedido do
     participante, evento adverso que contraindique a continuidade e **adesão < 50% das
     sessões previstas ao final da 2ª semana** — e diz que quem descontinua **permanece na
     análise por intenção de tratar**. Só o terceiro é regra automática; os outros dois são
     juízo humano e entram por endpoint de staff.

**Descontinuar não é retirar do estudo.** O participante sai da exposição (sessões passam a
403) e continua no denominador da análise: é o que ITT quer dizer, e é por isso que
``discontinued`` é um status diferente de ``withdrawn``.

**A regra nunca rebaixa um status mais forte.** Quem já foi retirado por segurança
(``removed``), retirou o consentimento (``withdrawn``) ou concluiu não vira ``discontinued`` —
a mesma precaução que o ADR-102 tomou com o ``erase``.
"""
from __future__ import annotations

import datetime as dt
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.email import EmailMessage, get_email_delivery
from app.core.models import (Allocation, Participant, ProtocolDiscontinuation,
                             SafetyAssessment, Session as SessionModel)
from app.core.protocol import (MIN_WEEK2_ADHERENCE_PCT, PRESCRIBED_SESSIONS, T2_WEEK,
                               adherence_pct, prescribed_through_week, study_day, study_week,
                               t2_window, week2_deadline)
from app.modules.audit.service import record_event

REASONS = ("solicitacao_participante", "evento_adverso", "adesao_insuficiente")

# Status que a descontinuação NÃO pode rebaixar (ver docstring do módulo).
STATUS_INTOCAVEIS = ("removed", "withdrawn", "completed")


def _allocation(db: Session, participant_id: uuid.UUID) -> Allocation | None:
    return db.scalar(select(Allocation).where(Allocation.participant_id == participant_id))


def completed_sessions(db: Session, participant_id: uuid.UUID, *,
                       before: dt.datetime | None = None) -> int:
    """Sessões que CONTAM para a adesão (>= 80% da duração; a régua é do servidor)."""
    q = select(func.count()).select_from(SessionModel).where(
        SessionModel.participant_id == participant_id, SessionModel.completed.is_(True))
    if before is not None:
        q = q.where(SessionModel.started_at < before)
    return int(db.scalar(q) or 0)


def t2_done(db: Session, participant_id: uuid.UUID, opens_at: dt.datetime) -> bool:
    """T2 respondida? Uma avaliação intermediária a partir da abertura da janela conta.

    Só a partir da abertura: um PHQ-9 respondido espontaneamente na 1ª semana é bem-vindo,
    mas não é a avaliação da 2ª semana — contá-lo faria o convite sumir antes da hora."""
    return db.scalar(select(SafetyAssessment.id).where(
        SafetyAssessment.participant_id == participant_id,
        SafetyAssessment.moment == "intermediaria",
        SafetyAssessment.assessed_at >= opens_at)) is not None


def discontinue(db: Session, participant_id: uuid.UUID, reason: str, *,
                decided_by: uuid.UUID | None = None,
                adverse_event_id: uuid.UUID | None = None,
                study_week_value: int | None = None,
                sessions_completed: int | None = None,
                sessions_prescribed: int | None = None) -> ProtocolDiscontinuation:
    """Registra a descontinuação (idempotente) e interrompe a exposição, mantendo o ITT."""
    if reason not in REASONS:
        raise ValueError(f"Motivo de descontinuação desconhecido: {reason!r}")
    ja = db.scalar(select(ProtocolDiscontinuation).where(
        ProtocolDiscontinuation.participant_id == participant_id))
    if ja is not None:
        return ja

    registro = ProtocolDiscontinuation(
        participant_id=participant_id, reason=reason, decided_by=decided_by,
        adverse_event_id=adverse_event_id, study_week=study_week_value,
        sessions_completed=sessions_completed, sessions_prescribed=sessions_prescribed,
        kept_in_itt=True)
    db.add(registro)
    db.flush()

    p = db.get(Participant, participant_id)
    if p is not None and p.status not in STATUS_INTOCAVEIS:
        p.status = "discontinued"
        db.flush()

    record_event(db, action="participant.discontinued", resource_type="participant",
                 actor_type="staff" if decided_by else "system", actor_id=decided_by,
                 resource_id=participant_id,
                 meta={"reason": reason, "study_week": study_week_value,
                       "sessions_completed": sessions_completed,
                       "sessions_prescribed": sessions_prescribed, "kept_in_itt": True})
    notify_team(registro.id, reason)
    return registro


def notify_team(discontinuation_id: uuid.UUID, reason: str) -> None:
    """Avisa a equipe. Best-effort, **sem PII** — o id do registro e o motivo bastam.

    A equipe precisa saber para conduzir a saída (contato, T4, relato ao CEP); quem precisa
    do código do participante entra na API de pesquisa. Sem ``TEAM_NOTIFY_EMAIL``, não
    notifica (item F3.7 do roadmap)."""
    to = os.getenv("TEAM_NOTIFY_EMAIL")
    if not to:
        return
    get_email_delivery().deliver(EmailMessage(
        to=to,
        subject="[Sereno] Descontinuação de protocolo registrada",
        body=(f"Um participante foi descontinuado do protocolo (registro {discontinuation_id}; "
              f"motivo: {reason}). Ele permanece na análise por intenção de tratar. "
              f"Detalhes na API de pesquisa."),
    ))


def evaluate_week2(db: Session, participant_id: uuid.UUID,
                   now: dt.datetime | None = None) -> ProtocolDiscontinuation | None:
    """Aplica a regra de adesão da 2ª semana. ``None`` se não é hora, ou se a adesão bastou.

    A contagem usa as sessões iniciadas ANTES do fim da 2ª semana: registrar uma sessão
    atrasada no dia 20 não pode reescrever o que aconteceu até o dia 14."""
    agora = now or dt.datetime.now(dt.timezone.utc)
    alloc = _allocation(db, participant_id)
    if alloc is None:
        return None
    prazo = week2_deadline(alloc.allocated_at)
    if agora < prazo:
        return None                      # a 2ª semana ainda não fechou
    p = db.get(Participant, participant_id)
    if p is None or p.status != "active":
        return None                      # já saiu por outro caminho; não rebaixa nem repete

    feitas = completed_sessions(db, participant_id, before=prazo)
    previstas = prescribed_through_week(T2_WEEK)
    if adherence_pct(feitas, previstas) >= MIN_WEEK2_ADHERENCE_PCT:
        return None
    return discontinue(db, participant_id, "adesao_insuficiente",
                       study_week_value=T2_WEEK, sessions_completed=feitas,
                       sessions_prescribed=previstas)


def sweep_week2(db: Session, now: dt.datetime | None = None) -> list[ProtocolDiscontinuation]:
    """Roda a regra da 2ª semana em todo mundo que ainda está ativo.

    Faz falta porque a avaliação preguiçosa (no início de sessão, na tela inicial) nunca
    alcança justamente quem parou de abrir o aplicativo — que é o caso que a regra existe
    para pegar."""
    ativos = db.scalars(
        select(Allocation.participant_id)
        .join(Participant, Participant.id == Allocation.participant_id)
        .where(Participant.status == "active")).all()
    saidas = [evaluate_week2(db, pid, now) for pid in ativos]
    return [s for s in saidas if s is not None]


def participant_progress(db: Session, participant_id: uuid.UUID,
                         now: dt.datetime | None = None) -> dict:
    """Onde o participante está: semana, adesão, T2 e (se houver) a descontinuação.

    Nada aqui depende do braço nem o revela — a jornada é idêntica nos dois (inegociável #1).
    Aplica a regra da 2ª semana de passagem: é o momento em que o servidor já tem tudo em mãos.
    """
    agora = now or dt.datetime.now(dt.timezone.utc)
    p = db.get(Participant, participant_id)
    alloc = _allocation(db, participant_id)

    if alloc is not None:
        evaluate_week2(db, participant_id, agora)
        p = db.get(Participant, participant_id)

    feitas = completed_sessions(db, participant_id)
    saida = db.scalar(select(ProtocolDiscontinuation).where(
        ProtocolDiscontinuation.participant_id == participant_id))

    corpo: dict = {
        "status": p.status if p is not None else "active",
        "allocated": alloc is not None,
        "study_day": None, "study_week": None,
        "sessions_completed": feitas,
        "sessions_prescribed": PRESCRIBED_SESSIONS,
        "adherence_pct": adherence_pct(feitas, PRESCRIBED_SESSIONS),
        "t2": None,
        "discontinuation": None,
    }
    if saida is not None:
        corpo["discontinuation"] = {"reason": saida.reason, "decided_at": saida.decided_at,
                                    "kept_in_itt": bool(saida.kept_in_itt)}
    if alloc is None:
        return corpo

    abre, fecha = t2_window(alloc.allocated_at)
    corpo["study_day"] = study_day(alloc.allocated_at, agora)
    corpo["study_week"] = study_week(alloc.allocated_at, agora)
    respondida = t2_done(db, participant_id, abre)
    corpo["t2"] = {
        "opens_at": abre, "closes_at": fecha,
        "due": abre <= agora and not respondida,
        "late": fecha < agora and not respondida,
        "completed": respondida,
    }
    return corpo
