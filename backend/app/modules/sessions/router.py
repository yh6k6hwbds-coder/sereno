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
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.db import get_db
from app.core.config import audio_max_gain, MIN_HEADPHONE_CHECK_ROUNDS
from app.core.security import require, current_participant
from app.core.problem import ProblemException
from app.core.rate_limit import enforce as rate_limit
from app.core.models import Session as SessionModel, PostSessionSurvey, AudioProtocol, Participant
from app.modules.allocation.service import resolve_arm
from app.modules.sessions.service import condition_for_arm, resolve_protocol, materialize_audio
from app.modules.sessions import storage
from app.modules.recommender.service import link_session
from app.modules.research.export_service import MIN_COMPLETION_RATIO

router = APIRouter(prefix="/sessions", tags=["sessions"])
# Entrega por URL ASSINADA (E3): endpoint público-mas-assinado, fora do prefixo /sessions.
audio_router = APIRouter(prefix="/audio", tags=["audio"])


class HeadphoneCheckIn(BaseModel):
    """Evidência da verificação DICÓTICA de fones (G4).

    Substitui a antiga declaração ``headphones_ok``: a condição dicótica é pré-requisito do
    fenômeno binaural, então é testada (o participante diz em qual orelha soou o sinal), não
    declarada. O sinal de teste é idêntico nos dois braços e não carrega condição."""
    version: str = Field(..., max_length=20)
    rounds: int = Field(..., ge=1, le=20)
    errors: int = Field(..., ge=0, le=20, description="erros NA TENTATIVA ACEITA (0)")
    attempts: int = Field(default=1, ge=1, le=50,
                          description="tentativas até passar (errar reinicia o teste)")
    ears: str | None = Field(default=None, max_length=20,
                             description="orelhas sorteadas, na ordem (auditoria do sorteio)")


class SessionStartIn(BaseModel):
    protocol_handle: str = Field(..., description="banda/handle NEUTRO quanto ao braço (ex.: 'delta')")
    headphone_check: HeadphoneCheckIn
    audio_gain: float = Field(..., gt=0.0, le=1.0,
                              description="ganho digital TRAVADO da reprodução (G3)")
    device_info: dict | None = None
    recommendation_id: uuid.UUID | None = Field(
        default=None, description="recomendação que originou esta sessão (opcional; p/ coerência)")


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
    # Fidelidade (inegociável): sem a verificação DICÓTICA aprovada, não inicia (G4).
    check = body.headphone_check
    if check.rounds < MIN_HEADPHONE_CHECK_ROUNDS:
        raise ProblemException(422, "Verificação de fones insuficiente",
                               "A verificação de fones precisa de pelo menos "
                               f"{MIN_HEADPHONE_CHECK_ROUNDS} rodadas.")
    if check.errors > 0:
        raise ProblemException(422, "Fones não verificados",
                               "A verificação de fones falhou; refaça antes de iniciar a sessão.")
    # Teto de volume imposto por software (G3): o participante não pode ultrapassá-lo.
    teto = audio_max_gain()
    if body.audio_gain > teto:
        raise ProblemException(422, "Volume acima do limite",
                               "O ganho de reprodução excede o limite do estudo.")
    # Consentimento retirado encerra a participação (LGPD; ADR-089) — não inicia sessão.
    p = db.get(Participant, participant_id)
    if p is not None and p.status == "withdrawn":
        raise ProblemException(403, "Consentimento retirado",
                               "Você retirou o consentimento; não é possível iniciar novas sessões.")
    # Retirado do protocolo pelo fluxo de segurança (G5/ADR-102): a exposição para aqui, e a
    # mensagem manda falar com a pesquisadora — não é punição nem diagnóstico na tela.
    if p is not None and p.status == "removed":
        raise ProblemException(403, "Participação interrompida",
                               "Sua participação no protocolo foi interrompida pela equipe do "
                               "estudo. Fale com a pesquisadora responsável.")
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
        headphones_ok=True,                       # derivado: a verificação acima passou
        headphone_check=check.model_dump(),        # evidência auditável, sem PII
        audio_gain=body.audio_gain,
        completed=False,
        interruptions=0,
        device_info=body.device_info,
    )
    db.add(s)
    db.flush()
    # Vínculo best-effort com a recomendação que originou a sessão (p/ o relatório de coerência).
    if body.recommendation_id is not None:
        link_session(db, participant_id, body.recommendation_id, s.id)
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
    # ``completed`` é o que a análise conta como ADESÃO (desfecho primário): o protocolo
    # exige pelo menos 80% da duração prescrita. Marcar toda sessão encerrada como concluída
    # inflaria a adesão — quem abriu o áudio por dois minutos contaria igual a quem ouviu os
    # vinte. A régua é do SERVIDOR (o cliente só relata o tempo efetivo) e usa a duração do
    # protocolo CONGELADO na sessão, não a do protocolo vigente hoje.
    proto = db.get(AudioProtocol, s.protocol_uuid)
    minimo = MIN_COMPLETION_RATIO * float(proto.duration_s) if proto is not None else 0.0
    s.completed = bool((s.effective_seconds or 0) >= minimo)
    db.flush()
    # Resposta NEUTRA quanto ao braço (a régua é a mesma nos dois): só diz se esta sessão
    # entra na contagem de adesão, o que o participante precisa saber para se organizar.
    return {"status": "recorded", "effective_seconds": s.effective_seconds,
            "counts_for_adherence": s.completed}


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


def _stream_audio(proto: AudioProtocol, request: Request) -> Response:
    """Materializa e transmite o WAV do protocolo, bit-a-bit, com headers NEUTROS.

    Forma da resposta IDÊNTICA entre braços — só os bytes (opacos) diferem. ``ETag`` =
    sha256 do corpo (integridade). Suporta um único Range (206) ou 416 se insatisfazível.
    Reusado pela entrega autenticada e pela entrega por URL assinada (E3)."""
    rendered = materialize_audio(proto)
    body = rendered.wav_bytes
    total = len(body)
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
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(content=body[start:end + 1], status_code=206,
                        media_type="audio/wav", headers=headers)
    return Response(content=body, status_code=200, media_type="audio/wav", headers=headers)


@router.get("/{session_id}/audio")
async def get_session_audio(session_id: uuid.UUID, request: Request,
                            db: DbSession = Depends(get_db),
                            participant_id: uuid.UUID = Depends(current_participant),
                            _user: dict = Depends(require("session:write"))):
    """Entrega o WAV da PRÓPRIA sessão, sem revelar o braço.

    O protocolo já foi resolvido e congelado na sessão (``protocol_uuid``); aqui não se
    re-resolve nem se decide condição. Por padrão transmite os bytes inline. Com
    ``AUDIO_DELIVERY=signed-url`` (E3), responde **302** para uma URL assinada de curta
    duração (chave = ``content_hash`` opaco) — a transferência sai do caminho autenticado."""
    # IDOR: a sessão precisa pertencer ao participante autenticado (404 não vaza existência).
    s = db.scalar(select(SessionModel).where(
        SessionModel.id == session_id, SessionModel.participant_id == participant_id))
    if s is None:
        raise ProblemException(404, "Sessão não encontrada", "Sessão inexistente para este participante.")
    proto = db.get(AudioProtocol, s.protocol_uuid)
    if proto is None:
        raise ProblemException(409, "Protocolo indisponível",
                               "O áudio desta sessão não está disponível na biblioteca.")
    if storage.signed_delivery_enabled():
        # Location NEUTRO: só content_hash opaco + exp + assinatura (nada do braço).
        return RedirectResponse(storage.build_signed_path(proto.content_hash), status_code=302)
    return _stream_audio(proto, request)


@audio_router.get("/{content_hash}")
async def get_signed_audio(content_hash: str, request: Request,
                           exp: str | None = None, sig: str | None = None,
                           db: DbSession = Depends(get_db)):
    """Entrega o WAV por URL ASSINADA (E3), sem ``Authorization``: a capability é a própria
    assinatura — exatamente como um signed URL de nuvem. A chave é o ``content_hash``
    **opaco** (já conhecido do cliente; não revela ativo/sham). Assinatura/validade
    inválidas → 403 genérico (sem oráculo). É a mesma resposta bit-a-bit do caminho autenticado.

    Por ser o ÚNICO endpoint público, é limitado por taxa por IP **antes** da verificação
    (ADR-090): assim o freio vale também para quem só varre assinaturas, e a força-bruta do
    HMAC não ganha um canal ilimitado. Limite generoso frente ao uso real (uma sessão baixa
    um arquivo, mais alguns Range); ajustável por ``AUDIO_RATE_LIMIT``/``AUDIO_RATE_WINDOW_S``."""
    rate_limit(request, bucket="audio", default_limit=60)
    if not storage.verify_signed(content_hash, exp, sig):
        raise ProblemException(403, "Assinatura inválida", "URL de áudio inválida ou expirada.")
    proto = db.scalar(select(AudioProtocol).where(AudioProtocol.content_hash == content_hash))
    if proto is None:
        raise ProblemException(404, "Áudio não encontrado", "Áudio inexistente na biblioteca.")
    return _stream_audio(proto, request)


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
