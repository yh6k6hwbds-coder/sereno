"""
modules/research/participants_service.py — Quem está no estudo (ADR-113).

Separado do router pela mesma razão dos outros serviços de pesquisa: a consulta tem regra
(adesão, contagem de eventos, paginação keyset) e regra com teste não vive em handler.

**O braço sai CODIFICADO (A/B) e nunca traduzido.** É como a área de pesquisa enxerga o estudo
inteiro — o relatório de análise já reporta por braço codificado —, e A/B não diz qual é o ativo:
o mapa fica selado até o *data lock*, com dois admins (ADR-075).
"""
from __future__ import annotations

import base64
import datetime as dt
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.models import AdverseEvent, Allocation, Participant, Session as SessionModel
from app.core.protocol import PRESCRIBED_SESSIONS, adherence_pct


def _encode_cursor(enrolled_at: dt.datetime, id_: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{enrolled_at.isoformat()}|{id_}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, id_ = raw.split("|", 1)
    return dt.datetime.fromisoformat(ts), uuid.UUID(id_)


def list_research_participants(db: Session, *, limit: int = 20,
                               cursor: str | None = None) -> dict:
    """Página de participantes, do mais recente para o mais antigo.

    Keyset em ``(enrolled_at, id)``, como a trilha de auditoria: dois participantes inscritos no
    mesmo instante empatariam, e um empate não resolvido faz páginas se repetirem ou pularem
    linhas — numa lista que a equipe usa para conferir quem está no estudo, isso é pior que
    lento.

    **As contagens saem por subconsulta, não por `join`.** Juntar sessões E eventos adversos na
    mesma linha multiplicaria uma pela outra (quem tem 20 sessões e 2 eventos apareceria com 40
    de cada), e a adesão sairia errada por um fator — o tipo de defeito que passa despercebido
    porque o número continua *parecendo* plausível."""
    concluidas = (select(func.count()).select_from(SessionModel)
                  .where(SessionModel.participant_id == Participant.id,
                         SessionModel.completed.is_(True))
                  .scalar_subquery())
    eventos = (select(func.count()).select_from(AdverseEvent)
               .where(AdverseEvent.participant_id == Participant.id)
               .scalar_subquery())

    stmt = (select(Participant.study_code, Participant.status, Participant.enrolled_at,
                   Participant.id, Allocation.arm_coded,
                   concluidas.label("concluidas"), eventos.label("eventos"))
            .outerjoin(Allocation, Allocation.participant_id == Participant.id)
            .order_by(Participant.enrolled_at.desc(), Participant.id.desc())
            .limit(limit + 1))
    if cursor:
        ts, cid = _decode_cursor(cursor)
        stmt = stmt.where(or_(
            Participant.enrolled_at < ts,
            and_(Participant.enrolled_at == ts, Participant.id < cid),
        ))

    linhas = list(db.execute(stmt).all())
    tem_mais = len(linhas) > limit
    linhas = linhas[:limit]
    proximo = (_encode_cursor(linhas[-1].enrolled_at, linhas[-1].id)
               if tem_mais and linhas else None)

    return {
        "items": [
            {
                "study_code": r.study_code,
                # Nulo = inscrito e ainda NÃO randomizado. É estado real do estudo.
                "arm_coded": r.arm_coded,
                "status": r.status,
                "adherence_pct": adherence_pct(r.concluidas, PRESCRIBED_SESSIONS),
                "sessions_completed": r.concluidas,
                "adverse_events": r.eventos,
                "enrolled_at": r.enrolled_at,
            }
            for r in linhas
        ],
        "next_cursor": proximo,
    }
