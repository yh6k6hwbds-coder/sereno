"""
binaural_instrument.py
======================
Núcleo de referência do "player como instrumento científico" para o piloto de
neuromodulação não invasiva (frequências binaurais).

Objetivo de engenharia: o estímulo é um INSTRUMENTO DE MEDIDA. Portanto a
geração precisa ser (1) determinística, (2) reprodutível/versionada e
(3) testável. Este módulo gera o sinal de forma determinística no BACKEND / na
pipeline de build (não em tempo real no aparelho), valida o sinal por FFT e
exporta um arquivo de áudio SEM PERDAS que o cliente reproduz bit-a-bit.

Conceito (batimento binaural):
    canal esquerdo (L) = seno(f_portadora)
    canal direito  (R) = seno(f_portadora + Δf)
    O "batimento" percebido (Δf) NÃO é uma frequência física em nenhum canal —
    surge centralmente (percepção). Por isso a validação confere a PUREZA
    ESPECTRAL de cada canal e a ATRIBUIÇÃO L/R, não um "pico de batimento".

Braço sham (placebo ativo):
    L = R = seno(f_portadora)  →  Δf = 0
    Idêntico ao ativo em portadora, amplitude, envelope, duração e (se houver)
    leito sonoro; difere APENAS pela ausência da diferença interaural. É o que
    preserva o cegamento em desfechos subjetivos.

Aviso: ferramenta complementar de pesquisa; não substitui avaliação/tratamento
profissional. Evidência de frequências binaurais é limitada e heterogênea.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import numpy as np


# ----------------------------------------------------------------------------
# Definição de protocolo (configuração reproduzível e versionada)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class AudioProtocol:
    """Define de forma reproduzível um estímulo do estudo.

    Um protocolo é imutável e versionado: qualquer mudança gera nova versão e
    novo hash. O hash entra no registro de cada sessão (rastreabilidade)."""
    protocol_id: str          # ex.: "alpha-10"
    version: str              # ex.: "1.0.0"
    band: str                 # "alpha" | "theta" | "delta"
    carrier_hz: float         # frequência portadora (ex.: 200.0)
    beat_hz: float            # Δf alvo do braço ATIVO (ex.: 10.0)
    duration_s: float         # duração total (inclui fades)
    fade_s: float = 3.0       # rampa raised-cosine de entrada/saída (evita cliques)
    target_peak_dbfs: float = -12.0   # teto/alvo de pico (segurança auditiva + consistência)
    sample_rate: int = 44100  # Hz
    bit_depth: int = 16       # PCM sem perdas

    def expected_channels_hz(self, sham: bool) -> tuple[float, float]:
        """Frequências esperadas (L, R). Sham → Δf = 0."""
        delta = 0.0 if sham else self.beat_hz
        return (self.carrier_hz, self.carrier_hz + delta)

    def content_hash(self, sham: bool) -> str:
        """Hash estável do conteúdo (identifica o arquivo renderizado)."""
        payload = {**asdict(self), "sham": sham}
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


# ----------------------------------------------------------------------------
# Síntese determinística
# ----------------------------------------------------------------------------
def _raised_cosine_envelope(n: int, fade_n: int) -> np.ndarray:
    """Envelope com fade-in/out raised-cosine (Hann) para evitar cliques."""
    env = np.ones(n, dtype=np.float64)
    if fade_n > 0:
        ramp = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fade_n)))
        env[:fade_n] = ramp
        env[-fade_n:] = ramp[::-1]
    return env


def synthesize(protocol: AudioProtocol, sham: bool = False,
               pink_noise_dbfs: float | None = None,
               seed: int = 20260101) -> np.ndarray:
    """Gera o sinal estéreo (float64 em [-1, 1]) de forma determinística.

    Parâmetros
    ----------
    sham : True gera o placebo ativo (Δf = 0).
    pink_noise_dbfs : nível de um leito de ruído rosa DIÓTICO (idêntico em L e R),
        opcional, para conforto/tolerabilidade. Sendo idêntico nos dois canais,
        não introduz pistas interaurais. None = sem leito (sinal puro).
    seed : semente do ruído (determinismo).
    """
    fs = protocol.sample_rate
    n = int(round(protocol.duration_s * fs))
    fade_n = int(round(protocol.fade_s * fs))
    t = np.arange(n, dtype=np.float64) / fs

    amp = 10.0 ** (protocol.target_peak_dbfs / 20.0)  # pico linear
    fL, fR = protocol.expected_channels_hz(sham)

    left = amp * np.sin(2.0 * np.pi * fL * t)
    right = amp * np.sin(2.0 * np.pi * fR * t)

    if pink_noise_dbfs is not None:
        bed = _pink_noise(n, seed=seed)
        bed *= (10.0 ** (pink_noise_dbfs / 20.0)) / (np.max(np.abs(bed)) + 1e-12)
        left = left + bed      # leito idêntico (diótico) nos dois canais
        right = right + bed

    env = _raised_cosine_envelope(n, fade_n)
    stereo = np.stack([left * env, right * env], axis=1)

    # margem de segurança: nunca exceder fundo de escala
    peak = np.max(np.abs(stereo))
    if peak > 1.0:
        stereo /= peak
    return stereo


def _pink_noise(n: int, seed: int) -> np.ndarray:
    """Ruído rosa (1/f) por filtragem no domínio da frequência (determinístico)."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n)
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    spectrum = spectrum / np.sqrt(freqs)   # 1/sqrt(f) em amplitude → 1/f em potência
    pink = np.fft.irfft(spectrum, n=n)
    return pink / (np.max(np.abs(pink)) + 1e-12)


def to_pcm(stereo: np.ndarray, bit_depth: int = 16) -> np.ndarray:
    """Converte float [-1,1] para PCM inteiro (sem perdas)."""
    if bit_depth == 16:
        return np.round(stereo * 32767.0).astype(np.int16)
    if bit_depth == 24 or bit_depth == 32:
        return np.round(stereo * 2147483647.0).astype(np.int32)
    raise ValueError("bit_depth deve ser 16, 24 ou 32")


# ----------------------------------------------------------------------------
# Validação por FFT (bateria de testes do sinal)
# ----------------------------------------------------------------------------
def _dbfs(x: float) -> float:
    return 20.0 * np.log10(max(x, 1e-12))


def _channel_spectrum(sig: np.ndarray, fs: int, seg_s: float = 4.0):
    """Espectro de um segmento em regime permanente (pós-fade), com janela Hann."""
    n_seg = int(round(seg_s * fs))
    start = (len(sig) - n_seg) // 2           # segmento central (fora dos fades)
    seg = sig[start:start + n_seg]
    win = np.hanning(len(seg))
    seg = seg * win
    mag = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), d=1.0 / fs)
    # compensação de ganho da janela para leitura de amplitude
    mag = mag / (np.sum(win) / 2.0)
    return freqs, mag


def validate_signal(stereo: np.ndarray, protocol: AudioProtocol, sham: bool,
                    freq_tol_hz: float = 0.3,
                    purity_floor_db: float = -60.0,
                    click_threshold: float = 0.05) -> dict:
    """Executa a bateria de validação e devolve um relatório estruturado.

    Verifica: (1) frequência de pico de cada canal = esperada; (2) atribuição
    L/R correta; (3) pureza espectral (energia fora do fundamental abaixo do
    piso); (4) pico ≤ teto de segurança; (5) fades sem cliques/descontinuidade.
    """
    fs = protocol.sample_rate
    exp_L, exp_R = protocol.expected_channels_hz(sham)
    report: dict = {"protocol": protocol.protocol_id, "version": protocol.version,
                    "sham": sham, "checks": [], "passed": True}

    def check(name, condition, detail):
        report["checks"].append({"check": name, "ok": bool(condition), "detail": detail})
        if not condition:
            report["passed"] = False

    peaks = {}
    for idx, (ch_name, exp) in enumerate([("L", exp_L), ("R", exp_R)]):
        freqs, mag = _channel_spectrum(stereo[:, idx], fs)
        k = int(np.argmax(mag))
        f_peak = float(freqs[k])
        peaks[ch_name] = f_peak

        # (1) frequência de pico correta
        check(f"{ch_name}: frequência de pico",
              abs(f_peak - exp) <= freq_tol_hz,
              f"pico={f_peak:.3f} Hz, esperado={exp:.3f} Hz")

        # (3) pureza espectral: energia fora de ±3 bins do fundamental
        guard = 3
        fund = mag[max(0, k - guard):k + guard + 1]
        total_e = float(np.sum(mag ** 2))
        fund_e = float(np.sum(fund ** 2))
        spur_ratio_db = _dbfs(np.sqrt(max(total_e - fund_e, 0.0) / (fund_e + 1e-18)))
        check(f"{ch_name}: pureza espectral",
              spur_ratio_db <= purity_floor_db,
              f"energia espúria={spur_ratio_db:.1f} dB (piso={purity_floor_db:.0f} dB)")

    # (2) atribuição L/R (guarda contra troca de canais)
    check("atribuição de canais L/R",
          abs(peaks["L"] - exp_L) <= freq_tol_hz and abs(peaks["R"] - exp_R) <= freq_tol_hz,
          f"L={peaks['L']:.3f} Hz (esp {exp_L:.1f}), R={peaks['R']:.3f} Hz (esp {exp_R:.1f})")

    # interaural real medido (deve bater com Δf do protocolo/sham)
    measured_delta = peaks["R"] - peaks["L"]
    exp_delta = 0.0 if sham else protocol.beat_hz
    check("diferença interaural (Δf)",
          abs(measured_delta - exp_delta) <= 2 * freq_tol_hz,
          f"Δf medido={measured_delta:.3f} Hz, esperado={exp_delta:.3f} Hz")

    # (4) teto de segurança auditiva / consistência de nível
    peak_dbfs = _dbfs(float(np.max(np.abs(stereo))))
    check("pico ≤ teto de segurança",
          peak_dbfs <= protocol.target_peak_dbfs + 0.5,
          f"pico={peak_dbfs:.2f} dBFS (teto={protocol.target_peak_dbfs:.1f} dBFS)")

    # (5) fades sem cliques: extremidades ~0 e sem salto amostra-a-amostra
    edge_ok = abs(stereo[0, 0]) < 1e-3 and abs(stereo[-1, 0]) < 1e-3
    max_jump = float(np.max(np.abs(np.diff(stereo, axis=0))))
    check("fades sem cliques",
          edge_ok and max_jump < click_threshold,
          f"|amostra inicial/final|~0={edge_ok}, salto máx={max_jump:.4f}")

    return report


# ----------------------------------------------------------------------------
# Biblioteca mínima de referência (portadora constante; varia só o Δf por banda).
# Exposta no módulo para ser reutilizada pelos testes e pelo gate de CI.
# ----------------------------------------------------------------------------
REFERENCE_LIBRARY = [
    AudioProtocol("alpha-10", "1.0.0", "alpha", 200.0, 10.0, duration_s=30.0),
    AudioProtocol("theta-6",  "1.0.0", "theta", 200.0,  6.0, duration_s=30.0),
    AudioProtocol("delta-2",  "1.0.0", "delta", 200.0,  2.0, duration_s=30.0),
]


def run_battery(library) -> bool:
    """Roda a bateria de validação por FFT sobre a biblioteca; devolve True se tudo passou.

    Este é o **gate inegociável de CI**: usa apenas numpy/scipy (nenhuma dependência de
    plotagem) para que a validação do estímulo nunca dependa de matplotlib."""
    print("=" * 70)
    print("VALIDAÇÃO DO INSTRUMENTO — síntese binaural + FFT")
    print("=" * 70)
    all_passed = True
    for proto in library:
        for sham in (False, True):
            sig = synthesize(proto, sham=sham)
            rep = validate_signal(sig, proto, sham=sham)
            all_passed &= rep["passed"]
            tag = "SHAM " if sham else "ATIVO"
            fL, fR = proto.expected_channels_hz(sham)
            print(f"\n[{tag}] {proto.protocol_id} v{proto.version} "
                  f"(L={fL:.0f} Hz, R={fR:.0f} Hz, Δf={fR-fL:.0f} Hz) "
                  f"hash={proto.content_hash(sham)}")
            for c in rep["checks"]:
                print(f"   {'✓' if c['ok'] else '✗'} {c['check']:32s} — {c['detail']}")
            print(f"   → RESULTADO: {'APROVADO' if rep['passed'] else 'REPROVADO'}")
    print("\n" + "=" * 70)
    print(f"BATERIA COMPLETA: {'TODOS APROVADOS' if all_passed else 'HÁ FALHAS'}")
    print("=" * 70)
    return all_passed


def render_validation_figure(library, out_dir: str | None = None) -> str | None:
    """Gera a figura FFT (ATIVO vs SHAM) do primeiro protocolo. OPCIONAL — fora do gate.

    Requer matplotlib; se ausente, apenas avisa e retorna ``None`` (a bateria de validação
    roda só com numpy/scipy). Devolve o caminho do PNG gerado ou ``None``."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[aviso] matplotlib ausente — figura de validação ignorada "
              "(a bateria FFT roda só com numpy/scipy).")
        return None
    import os

    NAVY, PETROL, CORAL = "#0B2447", "#19536B", "#D85A30"
    proto = library[0]
    fs = proto.sample_rate
    beat = proto.beat_hz
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6))
    for ax, sham, title in [(axes[0], False, f"Braço ATIVO — batimento binaural (Δf = {beat:.0f} Hz)"),
                            (axes[1], True,  "Braço SHAM — placebo ativo (Δf = 0)")]:
        sig = synthesize(proto, sham=sham)
        for idx, (ch, color) in enumerate([("Canal L", PETROL), ("Canal R", CORAL)]):
            freqs, mag = _channel_spectrum(sig[:, idx], fs)
            m = (freqs >= 150) & (freqs <= 260)
            ax.plot(freqs[m], 20 * np.log10(mag[m] / (np.max(mag) + 1e-12) + 1e-12),
                    color=color, lw=1.6, label=ch)
        exp_L, exp_R = proto.expected_channels_hz(sham)
        for f in {exp_L, exp_R}:
            ax.axvline(f, color=NAVY, ls="--", lw=0.8, alpha=0.55)
            ax.annotate(f"{f:.0f} Hz", xy=(f, 2), xytext=(f + 1.5, 2),
                        fontsize=9, color=NAVY)
        ax.set_title(title, fontsize=11, color=NAVY, fontweight="bold")
        ax.set_xlabel("Frequência (Hz)"); ax.set_ylabel("Magnitude (dB rel. ao pico)")
        ax.set_ylim(-90, 8); ax.set_xlim(150, 260)
        ax.grid(True, alpha=0.25); ax.legend(loc="upper right", fontsize=9, frameon=False)
    fig.suptitle("Validação por FFT do estímulo de referência — canais L/R por braço",
                 fontsize=12.5, color=NAVY, fontweight="bold", y=1.02)
    fig.tight_layout()
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "fft_validation.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"\nFigura salva em {path}")
    return path


# ----------------------------------------------------------------------------
# Demonstração executável / gate de CI (valida por FFT; figura é opcional)
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    passed = run_battery(REFERENCE_LIBRARY)
    # A figura é conveniência local: nunca bloqueia o gate nem exige matplotlib no CI.
    if "--no-plot" not in sys.argv:
        render_validation_figure(REFERENCE_LIBRARY)
    # Dentes do gate: código de saída ≠ 0 se qualquer protocolo reprovar na FFT.
    sys.exit(0 if passed else 1)
