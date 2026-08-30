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

**Parâmetros por protocolo, não por constante** (ADR-100): taxa de amostragem e rampas vêm da
linha do ``audio_protocol``, porque o estímulo do estudo tem 48 kHz e rampas assimétricas
(30 s de entrada, 60 s de saída) enquanto os protocolos curtos de demo/teste seguem em 44,1 kHz
com 3 s. Se isso fosse constante de módulo, trocar a constante mudaria em silêncio o estímulo
de um protocolo já auditado. **Síntese em blocos**: 20 min a 48 kHz são ~57,6 M amostras por
canal — de uma vez só em float64 seriam ~920 MB, então o sinal é gerado e quantizado em
janelas de 10 s (o resultado é idêntico, amostra a amostra).
"""
from __future__ import annotations

import hashlib
import io
import wave
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 44100          # Hz — padrão dos protocolos curtos (demo/teste)
CHANNELS = 2                 # estéreo (a diferença interaural é o próprio estímulo)
SAMPLE_WIDTH = 2             # bytes → PCM 16 bits, sem perdas
FADE_IN_S = 3.0              # rampa raised-cosine de entrada (padrão)
FADE_OUT_S = 3.0             # rampa raised-cosine de saída (padrão)
CHUNK_S = 10.0               # janela de síntese (memória limitada, resultado idêntico)
VALIDATION_WINDOW_S = 4.0    # trecho central usado na verificação por FFT
_INT16_MAX = 32767


@dataclass(frozen=True)
class RenderedAudio:
    """Resultado imutável da materialização: bytes do WAV + hash de integridade."""
    wav_bytes: bytes
    sha256: str               # sha256 hex do corpo — ETag e prova bit-a-bit
    sample_rate: int
    channels: int


def _ramp(fade_n: int) -> np.ndarray:
    """Rampa raised-cosine (Hann) de subida, com ``fade_n`` amostras."""
    if fade_n <= 1:
        return np.zeros(max(fade_n, 0), dtype=np.float64)
    return 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fade_n)))


def _clamped_fades(n: int, fade_in_n: int, fade_out_n: int) -> tuple[int, int]:
    """Nenhuma rampa passa da metade do sinal (protege durações curtas de demo/teste)."""
    half = n // 2
    return min(max(fade_in_n, 0), half), min(max(fade_out_n, 0), half)


def _envelope_slice(n: int, fade_in_n: int, fade_out_n: int,
                    start: int, count: int) -> np.ndarray:
    """Envelope do trecho ``[start, start+count)``, sem materializar o sinal inteiro."""
    fade_in_n, fade_out_n = _clamped_fades(n, fade_in_n, fade_out_n)
    env = np.ones(count, dtype=np.float64)
    idx = np.arange(start, start + count)
    if fade_in_n > 0:
        up = _ramp(fade_in_n)
        m = idx < fade_in_n
        env[m] = up[idx[m]]
    if fade_out_n > 0:
        down = _ramp(fade_out_n)[::-1]
        tail0 = n - fade_out_n
        m = idx >= tail0
        env[m] = down[idx[m] - tail0]
    return env


def synthesize_segment(carrier_hz: float, beat_hz: float, duration_s: float,
                       target_peak_dbfs: float, *, sample_rate: int = SAMPLE_RATE,
                       fade_in_s: float = FADE_IN_S, fade_out_s: float = FADE_OUT_S,
                       start: int = 0, count: int | None = None) -> np.ndarray:
    """Gera o trecho ``[start, start+count)`` do sinal estéreo (float64 em [-1, 1]).

    L = seno(portadora); R = seno(portadora + Δf). Para o sham (``beat_hz`` == 0), R coincide
    com L e não há pista interaural. A fase é contada desde a amostra 0 e o envelope é
    posicionado na duração TOTAL, então o trecho é idêntico ao pedaço correspondente do
    sinal inteiro."""
    fs = sample_rate
    n = int(round(duration_s * fs))
    if n <= 0:
        return np.zeros((0, CHANNELS), dtype=np.float64)
    count = n - start if count is None else min(count, n - start)
    if count <= 0:
        return np.zeros((0, CHANNELS), dtype=np.float64)

    amp = 10.0 ** (target_peak_dbfs / 20.0)           # pico linear
    f_left = carrier_hz
    f_right = carrier_hz + beat_hz                    # beat_hz == 0 (sham) → f_right == f_left
    t = (start + np.arange(count, dtype=np.float64)) / fs

    left = amp * np.sin(2.0 * np.pi * f_left * t)
    right = amp * np.sin(2.0 * np.pi * f_right * t)
    env = _envelope_slice(n, int(round(fade_in_s * fs)), int(round(fade_out_s * fs)),
                          start, count)
    stereo = np.stack([left * env, right * env], axis=1)

    peak = float(np.max(np.abs(stereo)))              # margem: nunca exceder fundo de escala
    if peak > 1.0:
        stereo /= peak
    return stereo


def synthesize_stereo(carrier_hz: float, beat_hz: float, duration_s: float,
                      target_peak_dbfs: float, *, sample_rate: int = SAMPLE_RATE,
                      fade_in_s: float = FADE_IN_S,
                      fade_out_s: float = FADE_OUT_S) -> np.ndarray:
    """Gera o sinal estéreo INTEIRO. Use apenas para durações curtas (demo/teste)."""
    return synthesize_segment(carrier_hz, beat_hz, duration_s, target_peak_dbfs,
                              sample_rate=sample_rate, fade_in_s=fade_in_s,
                              fade_out_s=fade_out_s)


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
    ``carrier_hz + beat_hz`` (para o sham, ambos na portadora ⇒ Δf medido = 0). Usa um
    trecho central limitado (regime permanente): a resolução já separa portadoras vizinhas
    e o custo não cresce com a duração da sessão.
    Levanta ``ValueError`` se algum canal fugir da tolerância. Retorna os picos medidos.
    """
    if stereo.shape[0] < 4:
        raise ValueError("Sinal curto demais para validação por FFT.")
    n_win = min(int(round(VALIDATION_WINDOW_S * sample_rate)), stereo.shape[0])
    ini = (stereo.shape[0] - n_win) // 2
    seg = stereo[ini:ini + n_win]
    window = np.hanning(n_win)
    freqs = np.fft.rfftfreq(n_win, d=1.0 / sample_rate)
    peaks: dict[str, float] = {}
    for idx, name in ((0, "L"), (1, "R")):
        mag = np.abs(np.fft.rfft(seg[:, idx] * window))
        peaks[name] = float(freqs[int(np.argmax(mag))])
    exp_l, exp_r = carrier_hz, carrier_hz + beat_hz
    if abs(peaks["L"] - exp_l) > freq_tol_hz or abs(peaks["R"] - exp_r) > freq_tol_hz:
        raise ValueError(
            f"FFT fora da tolerância: L={peaks['L']:.2f} (esp {exp_l:.2f}), "
            f"R={peaks['R']:.2f} (esp {exp_r:.2f})"
        )
    return peaks


def render_protocol(*, carrier_hz: float, beat_hz: float, duration_s: float,
                    target_peak_dbfs: float, sample_rate: int = SAMPLE_RATE,
                    fade_in_s: float = FADE_IN_S,
                    fade_out_s: float = FADE_OUT_S) -> RenderedAudio:
    """Sintetiza, VALIDA por FFT e serializa o WAV do protocolo. Fonte da verdade bit-a-bit.

    A síntese é feita em janelas de ``CHUNK_S`` para que a memória não cresça com a duração
    da sessão (20 min a 48 kHz de uma vez só seriam ~920 MB em float64)."""
    fs = int(sample_rate)
    n_total = int(round(duration_s * fs))
    common = dict(sample_rate=fs, fade_in_s=fade_in_s, fade_out_s=fade_out_s)
    # Teto digital tem de ser negativo: com pico ≥ 0 dBFS a normalização de segurança agiria
    # DENTRO de cada janela e blocos vizinhos sairiam com ganhos diferentes (degrau audível).
    if float(target_peak_dbfs) > 0.0:
        raise ValueError("target_peak_dbfs deve ser ≤ 0 dBFS.")

    # Verificação ANTES de serializar: um trecho central em regime permanente basta para
    # provar portadora, atribuição L/R e Δf — e não depende do tamanho da sessão.
    n_win = min(int(round(VALIDATION_WINDOW_S * fs)), max(n_total, 0))
    if n_win >= 4:
        probe = synthesize_segment(carrier_hz, beat_hz, duration_s, target_peak_dbfs,
                                   start=(n_total - n_win) // 2, count=n_win, **common)
        validate_fft(probe, float(carrier_hz), float(beat_hz), sample_rate=fs)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(fs)
        step = max(int(round(CHUNK_S * fs)), 1)
        for start in range(0, max(n_total, 0), step):
            chunk = synthesize_segment(carrier_hz, beat_hz, duration_s, target_peak_dbfs,
                                       start=start, count=min(step, n_total - start), **common)
            w.writeframes(_to_pcm16_bytes(chunk))
    wav_bytes = buf.getvalue()

    return RenderedAudio(
        wav_bytes=wav_bytes,
        sha256=hashlib.sha256(wav_bytes).hexdigest(),
        sample_rate=fs,
        channels=CHANNELS,
    )
