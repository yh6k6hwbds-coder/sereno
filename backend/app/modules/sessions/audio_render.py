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

**Formato de entrega** (ADR-103): o artefato materializado é **FLAC** por padrão — sem perdas,
o PCM decodificado é bit-a-bit igual ao do WAV (há teste que prova) e o estímulo, por ser um par
de senoides, comprime a ~14% do WAV: os 230 MB de 20 min a 48 kHz viram ~33 MB. ``AUDIO_FORMAT=wav``
volta ao PCM cru. O arquivo é escrito **direto no disco**, janela a janela: em nenhum momento o
processo segura a sessão inteira em memória (nem ao materializar, nem ao servir).

**Parâmetros por protocolo, não por constante** (ADR-100): taxa de amostragem e rampas vêm da
linha do ``audio_protocol``, porque o estímulo do estudo tem 48 kHz e rampas assimétricas
(30 s de entrada, 60 s de saída) enquanto os protocolos curtos de demo/teste seguem em 44,1 kHz
com 3 s. Se isso fosse constante de módulo, trocar a constante mudaria em silêncio o estímulo
de um protocolo já auditado. **Síntese em blocos**: 20 min a 48 kHz são ~57,6 M amostras por
canal — de uma vez só em float64 seriam ~920 MB, então o sinal é gerado e quantizado em
janelas de 10 s (o resultado é idêntico, amostra a amostra).
"""
from __future__ import annotations

import contextlib
import hashlib
import math
import os
import wave
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 44100          # Hz — padrão dos protocolos curtos (demo/teste)
CHANNELS = 2                 # estéreo (a diferença interaural é o próprio estímulo)
SAMPLE_WIDTH = 2             # bytes → PCM 16 bits, sem perdas
FADE_IN_S = 3.0              # rampa raised-cosine de entrada (padrão)
FADE_OUT_S = 3.0             # rampa raised-cosine de saída (padrão)
CHUNK_S = 10.0               # janela de síntese (memória limitada, resultado idêntico)
VALIDATION_WINDOW_S = 4.0    # trecho central usado na verificação por FFT
READ_CHUNK = 256 * 1024      # janela de leitura ao transmitir/hashear o arquivo
_INT16_MAX = 32767

# Formatos de entrega. Ambos são SEM PERDAS (inegociável #3): o FLAC decodifica para o
# mesmo PCM do WAV, amostra a amostra — o que muda é o tamanho do que trafega.
MEDIA_TYPES = {"wav": "audio/wav", "flac": "audio/flac"}
DEFAULT_FORMAT = "flac"


class EncoderUnavailable(RuntimeError):
    """O codificador do formato pedido não está instalado neste ambiente.

    Levantar é deliberado: cair em silêncio para WAV serviria 230 MB por sessão a um
    participante em 4G — a falha tem de ser visível a quem opera, não ao participante."""


def _soundfile():
    try:
        # Import tardio: só o caminho do FLAC depende do codificador.
        import soundfile
    except (ImportError, OSError) as e:   # OSError = libsndfile ausente no sistema
        raise EncoderUnavailable(
            "FLAC indisponível: instale 'soundfile' (libsndfile) ou use AUDIO_FORMAT=wav."
        ) from e
    return soundfile


@dataclass(frozen=True)
class RenderedAudio:
    """Handle imutável do artefato materializado — **caminho**, não bytes.

    Guardar bytes aqui obrigaria todo consumidor a carregar a sessão inteira na memória
    (230 MB por requisição no protocolo do estudo). O corpo é lido do disco em janelas,
    tanto para hashear quanto para transmitir."""
    path: str
    sha256: str               # sha256 hex do corpo servido — ETag e prova bit-a-bit
    size: int                 # bytes do arquivo (Content-Length / limites de Range)
    sample_rate: int
    channels: int
    fmt: str = DEFAULT_FORMAT

    @property
    def media_type(self) -> str:
        return MEDIA_TYPES[self.fmt]

    def chunks(self, start: int = 0, end: int | None = None,
               chunk_size: int = READ_CHUNK) -> Iterator[bytes]:
        """Lê o intervalo ``[start, end]`` (inclusivo) em janelas, direto do disco."""
        last = self.size - 1 if end is None else min(end, self.size - 1)
        restante = last - start + 1
        if restante <= 0:
            return
        with open(self.path, "rb") as f:
            f.seek(start)
            while restante > 0:
                bloco = f.read(min(chunk_size, restante))
                if not bloco:
                    return
                restante -= len(bloco)
                yield bloco

    def read_all(self) -> bytes:
        """Corpo inteiro em memória. Só para protocolos curtos (teste/demo)."""
        return b"".join(self.chunks())


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


# ----------------------------------------------------------------------------
# LEITO AMBIENTE (G2/ADR-109) — "trilha de fundo ambiental de baixa intensidade,
# idêntica em conteúdo, duração e nível, sobre a qual os tons são superpostos".
#
# **Estas constantes têm de ser IDÊNTICAS às de ``audio-pipeline/binaural_instrument.py``.**
# É a mesma duplicação já assumida para a fórmula dos tons (ver o cabeçalho deste módulo):
# a pipeline é a fonte de verdade científica, validada por FFT no CI; aqui está o
# materializador do servidor. Há teste que compara as duas sínteses amostra a amostra.
#
# É TONAL e vive entre 55 e 137,5 Hz — muito abaixo da banda do estímulo (250/253 Hz) —
# porque o protocolo recusa mascaramento; é DIÓTICO (a mesma coluna somada aos dois canais),
# então não carrega diferença interaural nenhuma; e é FÓRMULA FECHADA, sem gerador
# aleatório, para sair idêntico em janelas de 10 s e de uma vez só.
# ----------------------------------------------------------------------------
BED_PARTIALS_HZ = (55.0, 82.5, 110.0, 137.5)
BED_PARTIAL_GAINS = (1.0, 0.6, 0.4, 0.25)
BED_PARTIAL_PHASE = (0.0, 2.3, 4.1, 5.6)
BED_LFO_HZ = (0.037, 0.029, 0.051, 0.043)
BED_LFO_PHASE = (0.0, 1.7, 3.1, 4.6)
BED_AM_DEPTH = 0.35


def _bed_unit_rms() -> float:
    """RMS de longo prazo do leito unitário, em forma fechada (ver a pipeline)."""
    soma = sum(g * g / 2.0 for g in BED_PARTIAL_GAINS)
    return math.sqrt(soma * (1.0 + BED_AM_DEPTH ** 2 / 2.0))


def _bed_unit_peak_bound() -> float:
    """Cota superior do pico do leito unitário (parciais e LFOs todos em fase)."""
    return sum(BED_PARTIAL_GAINS) * (1.0 + BED_AM_DEPTH)


def bed_scale(target_peak_dbfs: float, bed_level_dbr: float | None) -> float:
    """Fator que põe o leito ``bed_level_dbr`` dB abaixo do RMS NOMINAL do estímulo."""
    if bed_level_dbr is None:
        return 0.0
    teto = 10.0 ** (target_peak_dbfs / 20.0)
    alvo_rms = (teto / math.sqrt(2.0)) * 10.0 ** (bed_level_dbr / 20.0)
    return alvo_rms / _bed_unit_rms()


def tone_amplitude(target_peak_dbfs: float, bed_level_dbr: float | None) -> float:
    """Amplitude dos tons: o teto digital MENOS a folga que o pico do leito ocupa.

    Sem leito é o próprio teto — um protocolo anterior a esta mudança gera exatamente as
    mesmas amostras de antes. Com leito, é o que impede o arquivo entregue de estourar o
    teto contra o qual a calibração em acoplador é feita."""
    teto = 10.0 ** (target_peak_dbfs / 20.0)
    return teto - bed_scale(target_peak_dbfs, bed_level_dbr) * _bed_unit_peak_bound()


def bed_segment(n_total: int, sample_rate: int, target_peak_dbfs: float,
                bed_level_dbr: float | None, *, start: int, count: int) -> np.ndarray:
    """Leito MONO do trecho ``[start, start+count)``, sem envelope (aplicado pelo chamador)."""
    if bed_level_dbr is None or count <= 0:
        return np.zeros(max(count, 0), dtype=np.float64)
    t = (start + np.arange(count, dtype=np.float64)) / sample_rate
    leito = np.zeros(count, dtype=np.float64)
    for f, g, ph, f_lfo, ph_lfo in zip(BED_PARTIALS_HZ, BED_PARTIAL_GAINS,
                                       BED_PARTIAL_PHASE, BED_LFO_HZ, BED_LFO_PHASE):
        am = 1.0 + BED_AM_DEPTH * np.sin(2.0 * np.pi * f_lfo * t + ph_lfo)
        leito += g * am * np.sin(2.0 * np.pi * f * t + ph)
    return leito * bed_scale(target_peak_dbfs, bed_level_dbr)


def synthesize_segment(carrier_hz: float, beat_hz: float, duration_s: float,
                       target_peak_dbfs: float, *, sample_rate: int = SAMPLE_RATE,
                       fade_in_s: float = FADE_IN_S, fade_out_s: float = FADE_OUT_S,
                       bed_level_dbr: float | None = None, with_bed: bool = True,
                       start: int = 0, count: int | None = None) -> np.ndarray:
    """Gera o trecho ``[start, start+count)`` do sinal estéreo (float64 em [-1, 1]).

    L = seno(portadora); R = seno(portadora + Δf). Para o sham (``beat_hz`` == 0), R coincide
    com L e não há pista interaural. A fase é contada desde a amostra 0 e o envelope é
    posicionado na duração TOTAL, então o trecho é idêntico ao pedaço correspondente do
    sinal inteiro.

    ``with_bed=False`` devolve só os TONS, e é diferente de passar ``bed_level_dbr=None``:
    a amplitude continua sendo a reduzida, que cedeu a folga do leito. A distinção é o que
    faz a subtração ``mistura − tons`` recuperar o leito limpo, e não a diferença de
    amplitude entre dois estímulos distintos (é como o gate da pipeline o isola — ADR-109)."""
    fs = sample_rate
    n = int(round(duration_s * fs))
    if n <= 0:
        return np.zeros((0, CHANNELS), dtype=np.float64)
    count = n - start if count is None else min(count, n - start)
    if count <= 0:
        return np.zeros((0, CHANNELS), dtype=np.float64)

    amp = tone_amplitude(target_peak_dbfs, bed_level_dbr)   # pico linear, já com a folga
    f_left = carrier_hz
    f_right = carrier_hz + beat_hz                    # beat_hz == 0 (sham) → f_right == f_left
    t = (start + np.arange(count, dtype=np.float64)) / fs

    left = amp * np.sin(2.0 * np.pi * f_left * t)
    right = amp * np.sin(2.0 * np.pi * f_right * t)
    env = _envelope_slice(n, int(round(fade_in_s * fs)), int(round(fade_out_s * fs)),
                          start, count)
    stereo = np.stack([left * env, right * env], axis=1)
    if bed_level_dbr is not None and with_bed:
        # Leito DIÓTICO sob o MESMO envelope: entra e sai junto com os tons, e por ser a
        # mesma coluna somada aos dois canais não carrega diferença interaural — nem
        # batimento que ninguém prescreveu, nem pista do braço (o leito não vê ``beat_hz``).
        leito = bed_segment(n, fs, target_peak_dbfs, bed_level_dbr, start=start, count=count)
        stereo = stereo + (leito * env)[:, None]

    peak = float(np.max(np.abs(stereo)))              # margem: nunca exceder fundo de escala
    if peak > 1.0:
        stereo /= peak
    return stereo


def _to_pcm16(stereo: np.ndarray) -> np.ndarray:
    """Quantiza float [-1, 1] → PCM 16 bits little-endian (determinístico), quadro a quadro."""
    clipped = np.clip(stereo, -1.0, 1.0)
    return np.round(clipped * _INT16_MAX).astype("<i2")


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


@contextlib.contextmanager
def _open_writer(path: str, fmt: str, sample_rate: int):
    """Abre o escritor do formato e devolve uma função que aceita blocos PCM int16.

    O tamanho dos blocos **não** muda o arquivo resultante em nenhum dos formatos (o WAV
    é PCM concatenado; o libFLAC reblocá antes de codificar) — há teste que fixa isso."""
    if fmt == "wav":
        w = wave.open(path, "wb")
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        try:
            yield lambda pcm: w.writeframes(pcm.tobytes())
        finally:
            w.close()
    elif fmt == "flac":
        sf = _soundfile()
        f = sf.SoundFile(path, mode="w", samplerate=int(sample_rate), channels=CHANNELS,
                         subtype="PCM_16", format="FLAC")
        try:
            yield f.write
        finally:
            f.close()
    else:
        raise ValueError(f"Formato de áudio desconhecido: {fmt!r}")


def read_pcm_window(path: str, fmt: str, start: int, count: int) -> np.ndarray:
    """Lê ``count`` quadros a partir de ``start`` do arquivo JÁ CODIFICADO (int16 → float).

    É por aqui que a validação por FFT passa a olhar o **artefato**, e não a síntese: com
    um codificador no caminho, validar o sinal em memória não prova mais o que será servido."""
    if fmt == "flac":
        sf = _soundfile()
        with sf.SoundFile(path) as f:
            f.seek(start)
            data = f.read(count, dtype="int16", always_2d=True)
    else:
        with wave.open(path, "rb") as w:
            w.setpos(start)
            raw = w.readframes(count)
        data = np.frombuffer(raw, dtype="<i2").reshape(-1, CHANNELS)
    return data.astype(np.float64) / _INT16_MAX


def sha256_of_file(path: str) -> tuple[str, int]:
    """(sha256 hex, tamanho) lendo o arquivo em janelas — nunca inteiro em memória."""
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as f:
        while bloco := f.read(READ_CHUNK):
            h.update(bloco)
            total += len(bloco)
    return h.hexdigest(), total


def render_protocol_to_file(dest: str, *, carrier_hz: float, beat_hz: float, duration_s: float,
                            target_peak_dbfs: float, sample_rate: int = SAMPLE_RATE,
                            fade_in_s: float = FADE_IN_S, fade_out_s: float = FADE_OUT_S,
                            bed_level_dbr: float | None = None,
                            fmt: str = DEFAULT_FORMAT) -> RenderedAudio:
    """Sintetiza, VALIDA por FFT e grava o artefato do protocolo em ``dest``.

    Duas validações, e as duas importam:
      1. **antes** de codificar, num trecho central sintetizado (regime permanente);
      2. **depois**, relendo o mesmo trecho **do arquivo gravado** — é o que prova que o
         codificador não alterou o estímulo (com FLAC no caminho, validar só a síntese
         deixaria de falar sobre o que o participante ouve).

    A síntese é feita em janelas de ``CHUNK_S`` e escrita direto no arquivo: a memória não
    cresce com a duração (20 min a 48 kHz de uma vez seriam ~920 MB em float64)."""
    fs = int(sample_rate)
    n_total = int(round(duration_s * fs))
    common = dict(sample_rate=fs, fade_in_s=fade_in_s, fade_out_s=fade_out_s,
                  bed_level_dbr=bed_level_dbr)
    # Teto digital tem de ser negativo: com pico ≥ 0 dBFS a normalização de segurança agiria
    # DENTRO de cada janela e blocos vizinhos sairiam com ganhos diferentes (degrau audível).
    if float(target_peak_dbfs) > 0.0:
        raise ValueError("target_peak_dbfs deve ser ≤ 0 dBFS.")
    if fmt not in MEDIA_TYPES:
        raise ValueError(f"Formato de áudio desconhecido: {fmt!r}")

    n_win = min(int(round(VALIDATION_WINDOW_S * fs)), max(n_total, 0))
    ini_win = (n_total - n_win) // 2
    if n_win >= 4:
        probe = synthesize_segment(carrier_hz, beat_hz, duration_s, target_peak_dbfs,
                                   start=ini_win, count=n_win, **common)
        validate_fft(probe, float(carrier_hz), float(beat_hz), sample_rate=fs)

    # Escrita em arquivo temporário: qualquer falha (disco, codificador, FFT) some com o
    # parcial em vez de deixá-lo no cache esperando para ser servido.
    tmp = dest + ".tmp"
    try:
        with _open_writer(tmp, fmt, fs) as escreve:
            step = max(int(round(CHUNK_S * fs)), 1)
            for start in range(0, max(n_total, 0), step):
                chunk = synthesize_segment(carrier_hz, beat_hz, duration_s, target_peak_dbfs,
                                           start=start, count=min(step, n_total - start),
                                           **common)
                escreve(_to_pcm16(chunk))

        if n_win >= 4:
            gravado = read_pcm_window(tmp, fmt, ini_win, n_win)
            validate_fft(gravado, float(carrier_hz), float(beat_hz), sample_rate=fs)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise

    os.replace(tmp, dest)          # publicação atômica: ninguém serve um arquivo parcial
    sha, size = sha256_of_file(dest)
    return RenderedAudio(path=dest, sha256=sha, size=size, sample_rate=fs,
                         channels=CHANNELS, fmt=fmt)
