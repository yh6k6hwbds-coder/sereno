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

from app.core.models import AudioProtocol
from app.modules.sessions import audio_render


def _sealed_map() -> dict[str, str]:
    """Mapa selado A/B → ativo/sham. Em produção: segredo em cofre, custodiado."""
    raw = os.getenv("ARM_CONDITION_MAP", "A:active,B:sham")
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
    """Diretório de cache dos WAV materializados (configurável; nunca versionado).

    Padrão: ``<backend>/.audio_cache`` (coberto por ``*.wav`` no .gitignore). Em produção,
    a entrega migra para armazenamento em nuvem (Fase E / ADR-070)."""
    default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        ".audio_cache",
    )
    return os.getenv("AUDIO_CACHE_DIR", default)


def materialize_audio(proto: AudioProtocol) -> audio_render.RenderedAudio:
    """Materializa (uma vez, com cache em disco) e devolve o WAV do protocolo já resolvido.

    O nome do arquivo usa ``content_hash`` (identidade OPACA do protocolo) — não revela a
    condição. Na primeira vez, sintetiza, VALIDA por FFT e grava o WAV + sidecar ``.sha256``;
    nas seguintes, relê do cache. O ``sha256`` retornado é a prova bit-a-bit (ETag)."""
    cache_dir = audio_cache_dir()
    wav_path = os.path.join(cache_dir, f"{proto.content_hash}.wav")
    sha_path = wav_path + ".sha256"

    if os.path.exists(wav_path) and os.path.exists(sha_path):
        with open(wav_path, "rb") as f:
            wav_bytes = f.read()
        with open(sha_path, "r", encoding="utf-8") as f:
            sha = f.read().strip()
        return audio_render.RenderedAudio(
            wav_bytes=wav_bytes, sha256=sha,
            sample_rate=audio_render.SAMPLE_RATE, channels=audio_render.CHANNELS,
        )

    with _MATERIALIZE_LOCK:
        # Reconfere sob o lock (outra requisição pode ter materializado enquanto esperávamos).
        if os.path.exists(wav_path) and os.path.exists(sha_path):
            return materialize_audio(proto)
        rendered = audio_render.render_protocol(
            carrier_hz=float(proto.carrier_hz), beat_hz=float(proto.beat_hz),
            duration_s=float(proto.duration_s), target_peak_dbfs=float(proto.target_peak_dbfs),
        )
        os.makedirs(cache_dir, exist_ok=True)
        # Escrita atômica (arquivo temporário + rename) para não servir um WAV parcial.
        tmp = wav_path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(rendered.wav_bytes)
        os.replace(tmp, wav_path)
        with open(sha_path, "w", encoding="utf-8") as f:
            f.write(rendered.sha256)
        return rendered
