"""
modules/sessions/router.py — Sessão + telemetria.

POST /v1/sessions (iniciar): exige verificação de fones; resolve o braço do
participante INTERNAMENTE (resolve_arm) e a condição (chave selada); grava a sessão
com protocol_hash; devolve APENAS session_id + handle neutro (banda) + content_hash.
Nunca retorna braço, condição ou beat_hz.
POST /v1/sessions/{id}/complete (encerrar): grava o que o protocolo manda registrar por
sessão (G10) — fim, duração efetiva, interrupções **e sua duração**, volume médio e máximo
aplicados e o item único de relaxamento (0 a 10). O teto de volume (G3) é reconferido sobre o
que foi REPRODUZIDO, não só sobre o que foi declarado ao iniciar.
Protegido contra IDOR (a sessão precisa ser do participante autenticado). problem+json.
"""
from __future__ import annotations
import datetime as dt
import uuid
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
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
from app.core.protocol import MIN_COMPLETION_RATIO
from app.modules.progress.service import evaluate_week2

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
    """Telemetria do fim da sessão — os itens que o protocolo manda registrar (G10).

    ``paused_seconds``, ``gain_mean``/``gain_peak`` e ``relaxation_0_10`` são **opcionais**:
    um cliente antigo (ou um reenvio da fila offline gravada antes desta versão) continua
    encerrando a sessão, e o campo fica nulo — a ausência é informação, e recusar o
    encerramento faria perder a medida de adesão, que é desfecho primário."""
    effective_seconds: int = Field(ge=0, le=86400)
    interruptions: int = Field(ge=0, default=0)
    paused_seconds: int | None = Field(
        default=None, ge=0, le=86400,
        description="tempo total em pausa (protocolo: 'interrupções e sua duração')")
    gain_mean: float | None = Field(
        default=None, gt=0.0, le=1.0, description="ganho MÉDIO aplicado na reprodução")
    gain_peak: float | None = Field(
        default=None, gt=0.0, le=1.0, description="ganho MÁXIMO aplicado na reprodução")
    relaxation_0_10: int | None = Field(
        default=None, ge=0, le=10,
        description="item único de percepção de relaxamento (0 a 10), por sessão")


class SessionSummaryOut(BaseModel):
    """Uma sessão como o PARTICIPANTE a vê: o próprio histórico, sem nada do protocolo.

    Sem ``content_hash`` e sem handle: no começo da sessão o cliente precisa deles para buscar
    o áudio, mas um histórico que os repita daria ao participante dois identificadores estáveis
    para comparar com os de outra pessoa — e duas pessoas com hashes diferentes saberiam que
    estão em braços diferentes. O histórico responde "o que eu já fiz", não "o que eu ouvi"."""
    session_id: uuid.UUID
    started_at: dt.datetime
    ended_at: dt.datetime | None
    completed: bool
    effective_seconds: int | None
    relaxation_0_10: int | None


class SessionSummaryPage(BaseModel):
    items: list[SessionSummaryOut]


class StaffSessionOut(BaseModel):
    """Uma sessão como a EQUIPE a vê: o registro que o protocolo manda manter (ADR-107).

    **Nada do protocolo de áudio sai daqui** — nem ``protocol_uuid``, nem ``protocol_hash``,
    nem a banda. Não é excesso de zelo: só existem dois protocolos, um por braço, então
    qualquer identificador estável do áudio particiona os participantes em dois grupos. Quem
    lê não saberia qual grupo é o ativo, mas saber **quem está com quem** já quebra o
    cegamento da análise — e o descegamento tem rito próprio, com dois admins (ADR-075)."""
    session_id: uuid.UUID
    study_code: str
    started_at: dt.datetime
    ended_at: dt.datetime | None
    completed: bool
    effective_seconds: int | None
    interruptions: int
    paused_seconds: int | None
    audio_gain: float | None
    gain_mean: float | None
    gain_peak: float | None
    relaxation_0_10: int | None
    headphones_ok: bool


class StaffSessionPage(BaseModel):
    items: list[StaffSessionOut]


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
    # Descontinuação de protocolo (G6/ADR-106). A regra da 2ª semana é aferida AQUI também:
    # é o momento em que alguém com adesão insuficiente voltaria a se expor, e o protocolo
    # já o descontinuou. Descontinuar não apaga nada — ele segue na análise por ITT.
    if evaluate_week2(db, participant_id) is not None:
        # A recusa logo abaixo é uma EXCEÇÃO, e exceção faz rollback da requisição inteira
        # (``get_db``). Sem este commit a descontinuação recém-decidida sumiria — e seria
        # redecidida (e reavisada à equipe) a cada nova tentativa de iniciar sessão.
        db.commit()
    p = db.get(Participant, participant_id)
    if p is not None and p.status == "discontinued":
        raise ProblemException(403, "Participação descontinuada",
                               "Sua participação no protocolo foi descontinuada. Os registros "
                               "já feitos permanecem no estudo; fale com a pesquisadora "
                               "responsável.")
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
    # G10 — o restante do registro por sessão. O teto de volume (G3) vale para o que foi
    # REPRODUZIDO, não só para o que foi declarado ao iniciar: um cliente que subisse o ganho
    # no meio da sessão passaria pela checagem do início e seria pego aqui.
    teto = audio_max_gain()
    if body.gain_peak is not None and body.gain_peak > teto:
        raise ProblemException(422, "Volume acima do limite",
                               "O ganho máximo reproduzido excede o limite do estudo.")
    if (body.gain_mean is not None and body.gain_peak is not None
            and body.gain_mean > body.gain_peak):
        raise ProblemException(422, "Volume inconsistente",
                               "O ganho médio não pode ser maior que o máximo.")
    s.paused_seconds = body.paused_seconds
    s.gain_mean = body.gain_mean
    s.gain_peak = body.gain_peak
    if body.relaxation_0_10 is not None:
        # Só preenche: o item pode chegar num reenvio posterior, e um envio sem ele não
        # deve apagar a resposta já dada.
        s.relaxation_0_10 = body.relaxation_0_10
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


def _etag_atende(if_none_match: str, etag: str) -> bool:
    """``If-None-Match`` casa com o ETag atual? (RFC 9110: lista, ``*``, prefixo ``W/``)."""
    for candidato in if_none_match.split(","):
        c = candidato.strip()
        if c == "*":
            return True
        if c.startswith("W/"):
            c = c[2:]
        if c.strip('"') == etag:
            return True
    return False


def _stream_audio(proto: AudioProtocol, request: Request) -> Response:
    """Materializa e transmite o artefato do protocolo, bit-a-bit, com headers NEUTROS.

    Forma da resposta IDÊNTICA entre braços — só os bytes (opacos) diferem. ``ETag`` =
    sha256 do corpo (integridade). Suporta um único Range (206) ou 416 se insatisfazível.
    Reusado pela entrega autenticada e pela entrega por URL assinada (E3).

    O corpo sai do **disco em janelas** (ADR-103): uma sessão do estudo tem 20 min e, em
    PCM cru, 230 MB — ler o corpo inteiro por requisição derrubaria o processo com poucos
    participantes simultâneos. O ``Content-Type`` acompanha o formato materializado e é o
    mesmo nos dois braços."""
    rendered = materialize_audio(proto)
    total = rendered.size
    headers = {
        "ETag": f'"{rendered.sha256}"',
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "Content-Length": str(total),
    }
    # Revalidação condicional: o app guarda o arquivo (cifrado) e pergunta, a cada sessão,
    # se ele continua valendo. São 20 sessões com o MESMO áudio — sem isto, o participante
    # rebaixaria dezenas de megabytes por sessão (ADR-103). O 304 não tem corpo, então sai
    # sem ``Content-Length``; a forma da resposta segue idêntica entre os braços.
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and _etag_atende(if_none_match, rendered.sha256):
        sem_corpo = {k: v for k, v in headers.items() if k != "Content-Length"}
        return Response(status_code=304, headers=sem_corpo)

    range_header = request.headers.get("range")
    if range_header:
        rng = _parse_range(range_header, total)
        if rng is None:
            raise ProblemException(416, "Faixa inválida",
                                   "O intervalo solicitado não pode ser satisfeito.")
        start, end = rng
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(rendered.chunks(start, end), status_code=206,
                                 media_type=rendered.media_type, headers=headers)
    return StreamingResponse(rendered.chunks(), status_code=200,
                             media_type=rendered.media_type, headers=headers)


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


def _num(v) -> float | None:
    """``Numeric`` volta do banco como ``Decimal``; o JSON do estudo fala em número."""
    return None if v is None else float(v)


@router.get("", response_model=SessionSummaryPage)
async def list_my_sessions(limit: int = 100, db: DbSession = Depends(get_db),
                           participant_id: uuid.UUID = Depends(current_participant),
                           _user: dict = Depends(require("session:write"))):
    """O histórico do próprio participante, do mais recente para o mais antigo.

    O contrato **já prometia** esta rota ("listar sessões do participante") e ela não existia:
    o módulo tinha o POST, o complete, o áudio e o questionário. Só devolve o que é do
    solicitante — o filtro por ``participant_id`` vem do token, nunca de parâmetro."""
    limit = max(1, min(limit, 500))
    linhas = db.scalars(
        select(SessionModel)
        .where(SessionModel.participant_id == participant_id)
        .order_by(SessionModel.started_at.desc(), SessionModel.id)
        .limit(limit)).all()
    return SessionSummaryPage(items=[
        SessionSummaryOut(
            session_id=x.id, started_at=x.started_at, ended_at=x.ended_at,
            completed=bool(x.completed), effective_seconds=x.effective_seconds,
            relaxation_0_10=x.relaxation_0_10)
        for x in linhas])


@router.get("/registry", response_model=StaffSessionPage)
async def list_sessions_for_staff(limit: int = 100, study_code: str | None = None,
                                  db: DbSession = Depends(get_db),
                                  _user: dict = Depends(require("research:read"))):
    """O registro por sessão que o protocolo manda manter, legível pela equipe (H2).

    O ADR-107 acrescentou as colunas que faltavam — duração das interrupções, volume médio e
    máximo, relaxamento 0–10 — e **nenhuma delas era legível**: existiam no banco e saíam, no
    máximo, agregadas no relatório. "Registro e monitoramento" é uma obrigação de manter dado
    recuperável, e dado que só o SQL alcança não está mantido para quem responde pelo estudo.

    Fica sob ``/sessions/registry``, e não em ``/research``, porque é o registro operacional da
    sessão — não a análise. ``study_code`` filtra por participante pelo mesmo pseudônimo que o
    resto da API da equipe usa; um código inexistente devolve lista vazia, não 404: a pergunta
    "este participante tem sessões?" tem "nenhuma" como resposta legítima."""
    limit = max(1, min(limit, 500))
    q = (select(SessionModel, Participant.study_code)
         .join(Participant, Participant.id == SessionModel.participant_id))
    if study_code is not None:
        q = q.where(Participant.study_code == study_code)
    linhas = db.execute(
        q.order_by(SessionModel.started_at.desc(), SessionModel.id).limit(limit)).all()
    return StaffSessionPage(items=[
        StaffSessionOut(
            session_id=x.id, study_code=code, started_at=x.started_at, ended_at=x.ended_at,
            completed=bool(x.completed), effective_seconds=x.effective_seconds,
            interruptions=x.interruptions, paused_seconds=x.paused_seconds,
            audio_gain=_num(x.audio_gain), gain_mean=_num(x.gain_mean),
            gain_peak=_num(x.gain_peak), relaxation_0_10=x.relaxation_0_10,
            headphones_ok=bool(x.headphones_ok))
        for x, code in linhas])
