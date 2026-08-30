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
    fade_in_s: float = 3.0    # rampa raised-cosine de ENTRADA (evita cliques)
    fade_out_s: float = 3.0   # rampa raised-cosine de SAÍDA (assimétrica: 30 s/60 s no piloto)
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
def _ramp(fade_n: int) -> np.ndarray:
    """Rampa raised-cosine (Hann) de SUBIDA, com ``fade_n`` amostras."""
    if fade_n <= 1:
        return np.zeros(max(fade_n, 0), dtype=np.float64)
    return 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fade_n)))


def _clamped_fades(n: int, fade_in_n: int, fade_out_n: int) -> tuple[int, int]:
    """Nenhuma rampa passa da metade do sinal (protege durações curtas de demo/teste)."""
    half = n // 2
    return min(max(fade_in_n, 0), half), min(max(fade_out_n, 0), half)


def _envelope_slice(n: int, fade_in_n: int, fade_out_n: int,
                    start: int, count: int) -> np.ndarray:
    """Envelope do trecho ``[start, start+count)`` SEM materializar o sinal inteiro.

    Necessário porque o estímulo do piloto tem 20 minutos: a 48 kHz, o sinal inteiro em
    float64 estéreo ocuparia ~920 MB — inviável para validar em CI ou renderizar no servidor.
    O resultado é idêntico, amostra a amostra, ao envelope calculado de uma vez só."""
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


def synthesize_segment(protocol: AudioProtocol, sham: bool = False, *,
                       start_s: float = 0.0,
                       duration_s: float | None = None) -> np.ndarray:
    """Gera APENAS o trecho ``[start_s, start_s + duration_s)`` do estímulo.

    Mesma fórmula canônica do sinal inteiro (fase contada desde a amostra 0 e envelope
    posicionado na duração TOTAL), então o trecho é bit-a-bit igual ao pedaço
    correspondente de ``synthesize``. É o caminho usado para validar e renderizar o
    estímulo de 20 minutos sem carregá-lo inteiro na memória."""
    fs = protocol.sample_rate
    n_total = int(round(protocol.duration_s * fs))
    start = int(round(start_s * fs))
    if start < 0 or start > n_total:
        raise ValueError("start_s fora do sinal.")
    count = n_total - start if duration_s is None else int(round(duration_s * fs))
    count = max(min(count, n_total - start), 0)
    if count == 0:
        return np.zeros((0, 2), dtype=np.float64)

    amp = 10.0 ** (protocol.target_peak_dbfs / 20.0)
    fL, fR = protocol.expected_channels_hz(sham)
    t = (start + np.arange(count, dtype=np.float64)) / fs

    left = amp * np.sin(2.0 * np.pi * fL * t)
    right = amp * np.sin(2.0 * np.pi * fR * t)
    env = _envelope_slice(n_total, int(round(protocol.fade_in_s * fs)),
                          int(round(protocol.fade_out_s * fs)), start, count)
    return np.stack([left * env, right * env], axis=1)


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
    stereo = synthesize_segment(protocol, sham=sham)
    if pink_noise_dbfs is not None:
        fs = protocol.sample_rate
        n = stereo.shape[0]
        bed = _pink_noise(n, seed=seed)
        bed *= (10.0 ** (pink_noise_dbfs / 20.0)) / (np.max(np.abs(bed)) + 1e-12)
        env = _envelope_slice(n, int(round(protocol.fade_in_s * fs)),
                              int(round(protocol.fade_out_s * fs)), 0, n)
        stereo = stereo + (bed * env)[:, None]        # leito diótico, sob o mesmo envelope

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


def _spectrum(seg: np.ndarray, fs: int):
    """Espectro (Hann, com compensação de ganho) de um segmento JÁ recortado."""
    win = np.hanning(len(seg))
    seg = seg * win
    mag = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), d=1.0 / fs)
    # compensação de ganho da janela para leitura de amplitude
    mag = mag / (np.sum(win) / 2.0)
    return freqs, mag


def _channel_spectrum(sig: np.ndarray, fs: int, seg_s: float = 4.0):
    """Espectro do trecho central (regime permanente, fora dos fades) de um sinal inteiro."""
    n_seg = min(int(round(seg_s * fs)), len(sig))
    start = (len(sig) - n_seg) // 2
    return _spectrum(sig[start:start + n_seg], fs)


def rms_dbfs(seg: np.ndarray) -> float:
    """Nível RMS do trecho em dBFS (base da equalização de energia entre os braços)."""
    return _dbfs(float(np.sqrt(np.mean(np.square(seg)))))


def _evidence(protocol: "AudioProtocol", sham: bool, stereo: np.ndarray | None = None,
              steady_s: float = 4.0, edge_s: float = 2.0) -> dict:
    """Colhe as evidências da validação: regime permanente (centro), início e fim.

    Com ``stereo`` (sinal inteiro) preserva a semântica antiga. Sem ele, sintetiza apenas os
    três trechos — é assim que um estímulo de 20 minutos é validado sem ocupar ~920 MB."""
    fs = protocol.sample_rate
    if stereo is not None:
        n_steady = min(int(round(steady_s * fs)), len(stereo))
        start = (len(stereo) - n_steady) // 2
        n_edge = min(int(round(edge_s * fs)), len(stereo))
        steady, head, tail = stereo[start:start + n_steady], stereo[:n_edge], stereo[-n_edge:]
        peak = float(np.max(np.abs(stereo)))
        max_jump = float(np.max(np.abs(np.diff(stereo, axis=0))))
    else:
        dur = protocol.duration_s
        steady_s = min(steady_s, dur)
        edge_s = min(edge_s, dur)
        steady = synthesize_segment(protocol, sham, start_s=max((dur - steady_s) / 2.0, 0.0),
                                    duration_s=steady_s)
        head = synthesize_segment(protocol, sham, start_s=0.0, duration_s=edge_s)
        tail = synthesize_segment(protocol, sham, start_s=dur - edge_s, duration_s=edge_s)
        peak = max(float(np.max(np.abs(s))) for s in (steady, head, tail))
        max_jump = max(float(np.max(np.abs(np.diff(s, axis=0)))) for s in (steady, head, tail))
    return {"steady": steady, "head": head, "tail": tail, "peak": peak, "max_jump": max_jump}


def validate_signal(stereo: np.ndarray, protocol: AudioProtocol, sham: bool,
                    freq_tol_hz: float = 0.3,
                    purity_floor_db: float = -60.0,
                    click_threshold: float = 0.05) -> dict:
    """Valida um sinal JÁ materializado (caminho de testes e de sinais curtos)."""
    return _validate(_evidence(protocol, sham, stereo=stereo), protocol, sham,
                     freq_tol_hz, purity_floor_db, click_threshold)


def validate_protocol(protocol: AudioProtocol, sham: bool,
                      freq_tol_hz: float = 0.3,
                      purity_floor_db: float = -60.0,
                      click_threshold: float = 0.05) -> dict:
    """Valida o protocolo sintetizando SÓ os trechos necessários (20 min cabe na memória)."""
    return _validate(_evidence(protocol, sham), protocol, sham,
                     freq_tol_hz, purity_floor_db, click_threshold)


def _validate(ev: dict, protocol: AudioProtocol, sham: bool,
              freq_tol_hz: float, purity_floor_db: float, click_threshold: float) -> dict:
    """Executa a bateria e devolve um relatório estruturado.

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
        freqs, mag = _spectrum(ev["steady"][:, idx], fs)
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
    peak_dbfs = _dbfs(ev["peak"])
    check("pico ≤ teto de segurança",
          peak_dbfs <= protocol.target_peak_dbfs + 0.5,
          f"pico={peak_dbfs:.2f} dBFS (teto={protocol.target_peak_dbfs:.1f} dBFS)")

    # (5) fades sem cliques: extremidades ~0 e sem salto amostra-a-amostra
    edge_ok = abs(ev["head"][0, 0]) < 1e-3 and abs(ev["tail"][-1, 0]) < 1e-3
    check("fades sem cliques",
          edge_ok and ev["max_jump"] < click_threshold,
          f"|amostra inicial/final|~0={edge_ok}, salto máx={ev['max_jump']:.4f}")

    return report


def validate_arm_energy_match(protocol: AudioProtocol, tol_db: float = 0.05) -> dict:
    """Confere a EQUALIZAÇÃO DE ENERGIA entre os braços (exigência do protocolo).

    O controle difere do ativo **apenas** pela diferença interaural: o nível RMS de cada
    canal, em regime permanente, tem de coincidir. Se um braço soasse mais alto que o outro,
    o participante ganharia uma pista audível e o cegamento cairia — por isso isto é um item
    do gate, e não uma consequência assumida da fórmula."""
    active = _evidence(protocol, sham=False)["steady"]
    sham_sig = _evidence(protocol, sham=True)["steady"]
    detail, ok = [], True
    for idx, ch in ((0, "L"), (1, "R")):
        d = abs(rms_dbfs(active[:, idx]) - rms_dbfs(sham_sig[:, idx]))
        ok &= d <= tol_db
        detail.append(f"{ch}: dif={d:.4f} dB")
    total = abs(rms_dbfs(active) - rms_dbfs(sham_sig))
    ok &= total <= tol_db
    return {"check": "energia equalizada entre braços", "ok": bool(ok),
            "detail": f"{', '.join(detail)}, total: dif={total:.4f} dB (tol={tol_db} dB)"}


# ----------------------------------------------------------------------------
# BIBLIOTECA DO PILOTO — o estímulo do protocolo aprovado. Fonte: seção
# "Protocolo de intervenção" do projeto de IC.
#
#   Braço experimental: 250 Hz na orelha ESQUERDA e 253 Hz na DIREITA
#                       (diferença interaural = batimento de 3 Hz, faixa delta).
#   Braço controle:     250 Hz idêntico nas duas orelhas (Δf = 0, sem batimento),
#                       energia acústica equalizada — é o mesmo protocolo com
#                       beat_hz = 0, e não um arquivo à parte.
#   Dose:               20 min por sessão (1200 s), 5 sessões/semana, 4 semanas.
#   Arquivo:            48 kHz, 16 bits, sem perdas; rampa de entrada de 30 s e
#                       de saída de 60 s (assimétrica, como especificado).
#
# A escolha dos parâmetros vem do protocolo (JIRAKITTAYAKORN; WONGSAWAT, 2018) e
# NÃO é decisão de engenharia: mudar qualquer número aqui é emenda de protocolo.
# O nível absoluto de 60 dB(A) é calibrado no acoplador de orelha; o que o arquivo
# carrega é o teto digital (``target_peak_dbfs``) contra o qual essa calibração é
# feita — ver docs/decisoes/ADR-100.
# ----------------------------------------------------------------------------
PILOT_LIBRARY = [
    AudioProtocol("delta-3", "1.0.0", "delta", 250.0, 3.0, duration_s=1200.0,
                  fade_in_s=30.0, fade_out_s=60.0, sample_rate=48000, bit_depth=16),
]

# ----------------------------------------------------------------------------
# Biblioteca de DESENVOLVIMENTO (curta): serve à demo local e a testes rápidos.
# NÃO é o estímulo do estudo — nenhum participante ouve isto.
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
            # Validação por TRECHOS: o estímulo de 20 min nunca é materializado inteiro.
            rep = validate_protocol(proto, sham=sham)
            all_passed &= rep["passed"]
            tag = "SHAM " if sham else "ATIVO"
            fL, fR = proto.expected_channels_hz(sham)
            print(f"\n[{tag}] {proto.protocol_id} v{proto.version} "
                  f"(L={fL:.0f} Hz, R={fR:.0f} Hz, Δf={fR-fL:.0f} Hz) "
                  f"hash={proto.content_hash(sham)}")
            for c in rep["checks"]:
                print(f"   {'✓' if c['ok'] else '✗'} {c['check']:32s} — {c['detail']}")
            print(f"   → RESULTADO: {'APROVADO' if rep['passed'] else 'REPROVADO'}")
        # Cegamento acústico: ativo e sham têm de ter a MESMA energia (item do gate).
        eq = validate_arm_energy_match(proto)
        all_passed &= eq["ok"]
        print(f"   {'✓' if eq['ok'] else '✗'} {eq['check']:32s} — {eq['detail']}")
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
    seg_s = min(4.0, proto.duration_s)
    seg_start = max((proto.duration_s - seg_s) / 2.0, 0.0)   # regime permanente
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6))
    for ax, sham, title in [(axes[0], False, f"Braço ATIVO — batimento binaural (Δf = {beat:.0f} Hz)"),
                            (axes[1], True,  "Braço SHAM — placebo ativo (Δf = 0)")]:
        sig = synthesize_segment(proto, sham=sham, start_s=seg_start, duration_s=seg_s)
        for idx, (ch, color) in enumerate([("Canal L", PETROL), ("Canal R", CORAL)]):
            freqs, mag = _spectrum(sig[:, idx], fs)
            lo, hi = proto.carrier_hz - 50.0, proto.carrier_hz + max(10.0, proto.beat_hz) + 10.0
            m = (freqs >= lo) & (freqs <= hi)
            ax.plot(freqs[m], 20 * np.log10(mag[m] / (np.max(mag) + 1e-12) + 1e-12),
                    color=color, lw=1.6, label=ch)
        exp_L, exp_R = proto.expected_channels_hz(sham)
        # Rótulos empilhados: com Δf de 3 Hz as duas linhas quase se tocam, e lado a lado
        # os textos se sobrepõem (a figura vai para o anexo do CEP).
        for i, f in enumerate(sorted({exp_L, exp_R})):
            ax.axvline(f, color=NAVY, ls="--", lw=0.8, alpha=0.55)
            ax.annotate(f"{f:.0f} Hz", xy=(f, 2), xytext=(f + 1.5, 2 - 9 * i),
                        fontsize=9, color=NAVY)
        ax.set_title(title, fontsize=11, color=NAVY, fontweight="bold")
        ax.set_xlabel("Frequência (Hz)"); ax.set_ylabel("Magnitude (dB rel. ao pico)")
        ax.set_ylim(-90, 8); ax.set_xlim(lo, hi)
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

    # O gate valida PRIMEIRO o estímulo do estudo e depois a biblioteca curta de dev.
    passed = run_battery(PILOT_LIBRARY)
    passed &= run_battery(REFERENCE_LIBRARY)
    # A figura é conveniência local: nunca bloqueia o gate nem exige matplotlib no CI.
    if "--no-plot" not in sys.argv:
        render_validation_figure(PILOT_LIBRARY)
    # Dentes do gate: código de saída ≠ 0 se qualquer protocolo reprovar na FFT.
    sys.exit(0 if passed else 1)
