"""
modules/sessions/audio_render.py — Materialização determinística do WAV da sessão.

O estímulo é um INSTRUMENTO de medida: a síntese é determinística e reprodutível.
Aqui o backend materializa (uma vez, em cache local) o WAV PCM **sem perdas** a partir
do ``AudioProtocol`` já resolvido e CONGELADO na sessão. Nada é re-resolvido neste módulo
e **o braço não é decidido aqui** — a condição (ativo/sham) já está embutida no protocolo
(``beat_hz`` > 0 = ativo; ``beat_hz`` == 0 = sham). O sham NÃO é tratado como caso especial:
com ``beat_hz`` == 0, o canal direito coincide com o esquerdo e Δf = 0 surge naturalmente.

Fidelidade (inegociável): o corpo servido é **bit-a-bit** igual a este WAV materializado; o
seu ``sha256`` (``audio_sha256``) é usado como ETag e prova de integridade — distinto do
``content_hash``, que permanece a identidade OPACA do protocolo (ver ADR-053).

A fórmula canônica é a mesma de ``audio-pipeline/binaural_instrument.py`` (portadora senoidal
em L, portadora + Δf em R, envelope raised-cosine para evitar cliques). A pipeline continua a
fonte de verdade *científica* (validada por FFT em CI); este módulo é o materializador do lado
do servidor e valida o próprio artefato antes de servir.
"""
from __future__ import annotations

import hashlib
import io
import wave
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 44100          # Hz — sem reamostragem no cliente (reprodução bit-a-bit)
CHANNELS = 2                 # estéreo (a diferença interaural é o próprio estímulo)
SAMPLE_WIDTH = 2             # bytes → PCM 16 bits, sem perdas
FADE_S = 3.0                 # rampa raised-cosine de entrada/saída (mesma da pipeline)
_INT16_MAX = 32767


@dataclass(frozen=True)
class RenderedAudio:
    """Resultado imutável da materialização: bytes do WAV + hash de integridade."""
    wav_bytes: bytes
    sha256: str               # sha256 hex do corpo — ETag e prova bit-a-bit
    sample_rate: int
    channels: int


def _raised_cosine_envelope(n: int, fade_n: int) -> np.ndarray:
    """Envelope com fade-in/out raised-cosine (Hann) para evitar cliques nas bordas."""
    env = np.ones(n, dtype=np.float64)
    fade_n = min(fade_n, n // 2)
    if fade_n > 0:
        ramp = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fade_n)))
        env[:fade_n] = ramp
        env[-fade_n:] = ramp[::-1]
    return env


def synthesize_stereo(carrier_hz: float, beat_hz: float, duration_s: float,
                      target_peak_dbfs: float, *, sample_rate: int = SAMPLE_RATE,
                      fade_s: float = FADE_S) -> np.ndarray:
    """Gera o sinal estéreo (float64 em [-1, 1]) de forma determinística.

    L = seno(portadora); R = seno(portadora + Δf). Para o sham (``beat_hz`` == 0),
    R coincide com L e não há pista interaural. O pico é fixado por ``target_peak_dbfs``
    (teto de segurança auditiva) e o envelope raised-cosine remove cliques.
    """
    fs = sample_rate
    n = int(round(duration_s * fs))
    if n <= 0:
        return np.zeros((0, CHANNELS), dtype=np.float64)
    fade_n = int(round(fade_s * fs))
    t = np.arange(n, dtype=np.float64) / fs

    amp = 10.0 ** (target_peak_dbfs / 20.0)          # pico linear
    f_left = carrier_hz
    f_right = carrier_hz + beat_hz                    # beat_hz == 0 (sham) → f_right == f_left

    left = amp * np.sin(2.0 * np.pi * f_left * t)
    right = amp * np.sin(2.0 * np.pi * f_right * t)

    env = _raised_cosine_envelope(n, fade_n)
    stereo = np.stack([left * env, right * env], axis=1)

    peak = float(np.max(np.abs(stereo)))             # margem: nunca exceder fundo de escala
    if peak > 1.0:
        stereo /= peak
    return stereo


def _to_pcm16_bytes(stereo: np.ndarray) -> bytes:
    """Quantiza float [-1, 1] → PCM 16 bits little-endian, intercalado L,R,L,R (determinístico)."""
    clipped = np.clip(stereo, -1.0, 1.0)
    ints = np.round(clipped * _INT16_MAX).astype("<i2")
    return ints.tobytes()


def encode_wav(stereo: np.ndarray, *, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Serializa o sinal em um WAV canônico (cabeçalho estável ⇒ bytes reprodutíveis)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(_to_pcm16_bytes(stereo))
    return buf.getvalue()


def validate_fft(stereo: np.ndarray, carrier_hz: float, beat_hz: float, *,
                 sample_rate: int = SAMPLE_RATE, freq_tol_hz: float = 1.0) -> dict[str, float]:
    """Valida por FFT o sinal materializado ANTES de servir.

    Confere a atribuição de canais: pico de L em ``carrier_hz`` e de R em
    ``carrier_hz + beat_hz`` (para o sham, ambos na portadora ⇒ Δf medido = 0).
    Levanta ``ValueError`` se algum canal fugir da tolerância. Retorna os picos medidos.
    """
    if stereo.shape[0] < 4:
        raise ValueError("Sinal curto demais para validação por FFT.")
    window = np.hanning(stereo.shape[0])
    freqs = np.fft.rfftfreq(stereo.shape[0], d=1.0 / sample_rate)
    peaks: dict[str, float] = {}
    for idx, name in ((0, "L"), (1, "R")):
        mag = np.abs(np.fft.rfft(stereo[:, idx] * window))
        peaks[name] = float(freqs[int(np.argmax(mag))])
    exp_l, exp_r = carrier_hz, carrier_hz + beat_hz
    if abs(peaks["L"] - exp_l) > freq_tol_hz or abs(peaks["R"] - exp_r) > freq_tol_hz:
        raise ValueError(
            f"FFT fora da tolerância: L={peaks['L']:.2f} (esp {exp_l:.2f}), "
            f"R={peaks['R']:.2f} (esp {exp_r:.2f})"
        )
    return peaks


def render_protocol(*, carrier_hz: float, beat_hz: float, duration_s: float,
                    target_peak_dbfs: float) -> RenderedAudio:
    """Sintetiza, VALIDA por FFT e serializa o WAV do protocolo. Fonte da verdade bit-a-bit."""
    stereo = synthesize_stereo(float(carrier_hz), float(beat_hz), float(duration_s),
                               float(target_peak_dbfs))
    validate_fft(stereo, float(carrier_hz), float(beat_hz))
    wav_bytes = encode_wav(stereo)
    return RenderedAudio(
        wav_bytes=wav_bytes,
        sha256=hashlib.sha256(wav_bytes).hexdigest(),
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
    )
