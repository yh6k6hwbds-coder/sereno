"""
modules/sessions/service.py — Resolução INTERNA de áudio (ativo/sham) por braço.

O mapa A/B → ativo/sham é a CHAVE SELADA: fica fora do banco (variável de ambiente /
cofre), nunca em consulta que ligue participante→condição. `resolve_protocol` escolhe
o arquivo concreto a partir da banda (neutra quanto ao braço) + condição. Nada aqui é
exposto por API. Fidelidade: o cliente reproduz o arquivo (content_hash) bit-a-bit.
"""
from __future__ import annotations
import os
import threading
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import (is_production, InsecureConfigError, DEV_ARM_CONDITION_MAP,
                             audio_format)
from app.core.models import AudioProtocol
from app.modules.sessions import audio_render


def _sealed_map() -> dict[str, str]:
    """Mapa selado A/B → ativo/sham. Em produção: secret custodiado, JAMAIS o default.

    Defesa em profundidade: mesmo que o guard de startup (``config.validate_runtime_config``)
    seja contornado, aqui recusamos resolver a condição com o default público em produção —
    isso revelaria ativo/sham a partir do braço codificado A/B (inegociável #2)."""
    raw = os.getenv("ARM_CONDITION_MAP")
    if raw is None:
        if is_production():
            raise InsecureConfigError(
                "ARM_CONDITION_MAP ausente em produção: recuso resolver a condição com o "
                "default público (quebraria o cegamento — inegociável #2).")
        raw = DEV_ARM_CONDITION_MAP
    m: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            k, v = pair.split(":", 1)
            m[k.strip()] = v.strip()
    return m


def condition_for_arm(arm: str) -> str | None:
    """Traduz o braço codificado (A/B) em condição (active/sham). INTERNO."""
    return _sealed_map().get(arm)


def resolve_protocol(db: DbSession, band: str, condition: str) -> AudioProtocol | None:
    """Escolhe o protocolo concreto: mesma banda; ativo = beat_hz>0, sham = beat_hz==0."""
    q = select(AudioProtocol).where(AudioProtocol.band == band)
    q = q.where(AudioProtocol.beat_hz > 0) if condition == "active" else q.where(AudioProtocol.beat_hz == 0)
    return db.scalars(q).first()


# ---------------------------------------------------------------------------
# Materialização/entrega de áudio (A1)
# ---------------------------------------------------------------------------
_MATERIALIZE_LOCK = threading.Lock()


def audio_cache_dir() -> str:
    """Diretório de cache dos artefatos materializados (configurável; nunca versionado).

    Padrão: ``<backend>/.audio_cache`` (coberto por ``*.wav`` no .gitignore). A entrega por
    URL assinada (E3/ADR-082) já sai deste cache; o offload para nuvem encaixa na porta
    ``AudioStorage`` (``modules/sessions/storage.py``)."""
    default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        ".audio_cache",
    )
    return os.getenv("AUDIO_CACHE_DIR", default)


def materialize_audio(proto: AudioProtocol) -> audio_render.RenderedAudio:
    """Materializa (uma vez, com cache em disco) o artefato do protocolo já resolvido.

    Devolve um **handle** (caminho + sha256 + tamanho), não os bytes: o corpo é lido do
    disco em janelas na hora de servir, então nem materializar nem transmitir carrega a
    sessão inteira na memória do processo (ADR-103). O nome do arquivo usa ``content_hash``
    (identidade OPACA do protocolo) — não revela a condição; a extensão vem do formato.
    Na primeira vez sintetiza, VALIDA por FFT (antes e depois de codificar) e grava o
    artefato + o sidecar ``.sha256``; nas seguintes, relê o sidecar."""
    fmt = audio_format()
    cache_dir = audio_cache_dir()
    path = os.path.join(cache_dir, f"{proto.content_hash}.{fmt}")
    sha_path = path + ".sha256"

    def _handle(sha: str) -> audio_render.RenderedAudio:
        return audio_render.RenderedAudio(
            path=path, sha256=sha, size=os.path.getsize(path),
            sample_rate=int(proto.sample_rate), channels=audio_render.CHANNELS, fmt=fmt)

    if os.path.exists(path) and os.path.exists(sha_path):
        with open(sha_path, "r", encoding="utf-8") as f:
            return _handle(f.read().strip())

    with _MATERIALIZE_LOCK:
        # Reconfere sob o lock (outra requisição pode ter materializado enquanto esperávamos).
        if os.path.exists(path) and os.path.exists(sha_path):
            with open(sha_path, "r", encoding="utf-8") as f:
                return _handle(f.read().strip())
        os.makedirs(cache_dir, exist_ok=True)
        rendered = audio_render.render_protocol_to_file(
            path,
            carrier_hz=float(proto.carrier_hz), beat_hz=float(proto.beat_hz),
            duration_s=float(proto.duration_s), target_peak_dbfs=float(proto.target_peak_dbfs),
            sample_rate=int(proto.sample_rate), fade_in_s=float(proto.fade_in_s),
            fade_out_s=float(proto.fade_out_s), fmt=fmt,
        )
        # Sidecar por último: sua existência é o sinal de "artefato completo e conferido".
        with open(sha_path, "w", encoding="utf-8") as f:
            f.write(rendered.sha256)
        return rendered
