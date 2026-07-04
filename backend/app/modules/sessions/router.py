"""
modules/sessions/router.py — Sessão + telemetria.

POST /v1/sessions (iniciar): exige verificação de fones; resolve o braço do
participante INTERNAMENTE (resolve_arm) e a condição (chave selada); grava a sessão
com protocol_hash; devolve APENAS session_id + handle neutro (banda) + content_hash.
Nunca retorna braço, condição ou beat_hz.
POST /v1/sessions/{id}/complete (encerrar): grava fim, duração efetiva e interrupções.
Protegido contra IDOR (a sessão precisa ser do participante autenticado). problem+json.
"""
from __future__ import annotations
import datetime as dt
import uuid
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_db
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.models import Session as SessionModel, PostSessionSurvey, AudioProtocol
from app.modules.allocation.service import resolve_arm
from app.modules.sessions.service import condition_for_arm, resolve_protocol, materialize_audio

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionStartIn(BaseModel):
    protocol_handle: str = Field(..., description="banda/handle NEUTRO quanto ao braço (ex.: 'alpha')")
    headphones_ok: bool
    device_info: dict | None = None


class SessionStartOut(BaseModel):
    session_id: uuid.UUID
    protocol_handle: str          # ecoado (banda) — igual nos dois braços
    content_hash: str             # opaco; o cliente reproduz o arquivo bit-a-bit
    started_at: dt.datetime


class SessionCompleteIn(BaseModel):
    effective_seconds: int = Field(ge=0, le=86400)
    interruptions: int = Field(ge=0, default=0)


@router.get("/_status")
async def status():
    return {"module": "sessions", "status": "stub"}


@router.post("", status_code=201, response_model=SessionStartOut)
async def start_session(body: SessionStartIn, db: DbSession = Depends(get_db),
                        participant_id: uuid.UUID = Depends(current_participant),
                        _user: dict = Depends(require("session:write"))):
    # Fidelidade (inegociável): sem fones verificados, não inicia.
    if not body.headphones_ok:
        raise ProblemException(422, "Fones não verificados",
                               "Verifique fones estéreo antes de iniciar a sessão.")
    # Resolução do braço é INTERNA — o cliente nunca a vê.
    arm = resolve_arm(db, participant_id)
    if arm is None:
        raise ProblemException(409, "Participante não alocado",
                               "É necessário alocar o participante antes de iniciar sessões.")
    condition = condition_for_arm(arm)      # chave selada A/B → active/sham
    proto = resolve_protocol(db, body.protocol_handle, condition)
    if proto is None:
        raise ProblemException(409, "Protocolo indisponível",
                               "A biblioteca de áudio não contém o protocolo solicitado.")

    s = SessionModel(
        participant_id=participant_id,
        protocol_uuid=proto.id,
        protocol_hash=proto.content_hash,
        started_at=dt.datetime.now(dt.timezone.utc),
        headphones_ok=True,
        completed=False,
        interruptions=0,
        device_info=body.device_info,
    )
    db.add(s)
    db.flush()
    # Resposta NEUTRA: handle da banda (igual nos dois braços) + hash opaco.
    return SessionStartOut(session_id=s.id, protocol_handle=body.protocol_handle,
                           content_hash=proto.content_hash, started_at=s.started_at)


@router.post("/{session_id}/complete")
async def complete_session(session_id: uuid.UUID, body: SessionCompleteIn,
                           db: DbSession = Depends(get_db),
                           participant_id: uuid.UUID = Depends(current_participant),
                           _user: dict = Depends(require("session:write"))):
    # IDOR: a sessão precisa pertencer ao participante autenticado.
    s = db.scalar(select(SessionModel).where(
        SessionModel.id == session_id, SessionModel.participant_id == participant_id))
    if s is None:
        raise ProblemException(404, "Sessão não encontrada", "Sessão inexistente para este participante.")
    s.ended_at = dt.datetime.now(dt.timezone.utc)
    s.effective_seconds = body.effective_seconds
    s.interruptions = body.interruptions
    s.completed = True
    db.flush()
    return {"status": "completed", "effective_seconds": s.effective_seconds}


def _parse_range(header: str, total: int) -> tuple[int, int] | None:
    """Interpreta um único intervalo ``bytes=<ini>-<fim>`` (RFC 9110).

    Devolve ``(inicio, fim)`` inclusivos, ou ``None`` se o intervalo for insatisfazível
    (o chamador responde 416). Suporta ``bytes=ini-``, ``bytes=ini-fim`` e sufixo
    ``bytes=-n`` (últimos n bytes). Não trata multi-range (fora do escopo do piloto)."""
    if not header.startswith("bytes=") or total <= 0:
        return None
    spec = header[len("bytes="):].split(",")[0].strip()
    if "-" not in spec:
        return None
    ini_s, fim_s = spec.split("-", 1)
    try:
        if ini_s == "":                       # sufixo: últimos N bytes
            n = int(fim_s)
            if n <= 0:
                return None
            start = max(total - n, 0)
            return (start, total - 1)
        start = int(ini_s)
        end = int(fim_s) if fim_s != "" else total - 1
    except ValueError:
        return None
    end = min(end, total - 1)
    if start > end or start < 0:
        return None
    return (start, end)


@router.get("/{session_id}/audio")
async def get_session_audio(session_id: uuid.UUID, request: Request,
                            db: DbSession = Depends(get_db),
                            participant_id: uuid.UUID = Depends(current_participant),
                            _user: dict = Depends(require("session:write"))):
    """Transmite o WAV da PRÓPRIA sessão, bit-a-bit, sem revelar o braço.

    O protocolo já foi resolvido e congelado na sessão (``protocol_uuid``); aqui não se
    re-resolve nem se decide condição. Headers e forma da resposta são IDÊNTICOS entre
    braços — só os bytes (opacos) diferem. ``ETag`` = sha256 do corpo (integridade)."""
    # IDOR: a sessão precisa pertencer ao participante autenticado (404 não vaza existência).
    s = db.scalar(select(SessionModel).where(
        SessionModel.id == session_id, SessionModel.participant_id == participant_id))
    if s is None:
        raise ProblemException(404, "Sessão não encontrada", "Sessão inexistente para este participante.")
    proto = db.get(AudioProtocol, s.protocol_uuid)
    if proto is None:
        raise ProblemException(409, "Protocolo indisponível",
                               "O áudio desta sessão não está disponível na biblioteca.")

    rendered = materialize_audio(proto)
    body = rendered.wav_bytes
    total = len(body)
    # Headers NEUTROS (iguais nos dois braços). ETag identifica os BYTES (não a condição).
    headers = {
        "ETag": f'"{rendered.sha256}"',
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
    }

    range_header = request.headers.get("range")
    if range_header:
        rng = _parse_range(range_header, total)
        if rng is None:
            raise ProblemException(416, "Faixa inválida",
                                   "O intervalo solicitado não pode ser satisfeito.")
        start, end = rng
        chunk = body[start:end + 1]
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(content=chunk, status_code=206, media_type="audio/wav", headers=headers)

    return Response(content=body, status_code=200, media_type="audio/wav", headers=headers)


class SurveyIn(BaseModel):
    feeling: int = Field(ge=0, le=4)
    relaxation: int = Field(ge=0, le=4)
    slept_better: int | None = Field(default=None, ge=0, le=4)
    liked: int = Field(ge=0, le=4)
    intensity: int = Field(ge=0, le=4)
    would_repeat: bool


@router.post("/{session_id}/survey", status_code=201)
async def submit_survey(session_id: uuid.UUID, body: SurveyIn,
                        db: DbSession = Depends(get_db),
                        participant_id: uuid.UUID = Depends(current_participant),
                        _user: dict = Depends(require("session:write"))):
    # IDOR: a sessão precisa ser do participante autenticado.
    s = db.scalar(select(SessionModel).where(
        SessionModel.id == session_id, SessionModel.participant_id == participant_id))
    if s is None:
        raise ProblemException(404, "Sessão não encontrada", "Sessão inexistente para este participante.")
    if db.scalar(select(PostSessionSurvey.id).where(PostSessionSurvey.session_id == session_id)) is not None:
        raise ProblemException(409, "Questionário já enviado", "Esta sessão já possui questionário.")
    db.add(PostSessionSurvey(
        session_id=session_id, feeling=body.feeling, relaxation=body.relaxation,
        slept_better=body.slept_better, liked=body.liked, intensity=body.intensity,
        would_repeat=body.would_repeat, answered_at=dt.datetime.now(dt.timezone.utc)))
    db.flush()
    return {"status": "recorded"}
