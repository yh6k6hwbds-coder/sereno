"""
tests/test_pilot_protocol.py — O estímulo do PROTOCOLO APROVADO (não o de desenvolvimento).

Guarda os números que vêm do projeto de pesquisa, não da engenharia:

    braço experimental — 250 Hz na orelha esquerda, 253 Hz na direita (Δf = 3 Hz, delta);
    braço controle     — 250 Hz idêntico nas duas orelhas (Δf = 0), energia equalizada;
    arquivo            — 20 min, 48 kHz, 16 bits, sem perdas, rampas de 30 s / 60 s;
    leito ambiente     — trilha de fundo tonal, diótica, "de baixa intensidade" (ADR-109).

Mudar qualquer um destes valores é EMENDA DE PROTOCOLO (CEP), não refatoração: por isso
o teste falha na cara de quem editar a biblioteca sem passar pelo comitê.
"""
from __future__ import annotations

import numpy as np

import binaural_instrument as bi


def _pilot():
    assert len(bi.PILOT_LIBRARY) == 1, "o piloto usa UM protocolo fixo (sem personalização)"
    return bi.PILOT_LIBRARY[0]


def test_parametros_do_protocolo_aprovado():
    p = _pilot()
    assert (p.carrier_hz, p.beat_hz, p.band) == (250.0, 3.0, "delta")
    assert p.expected_channels_hz(sham=False) == (250.0, 253.0)
    assert p.expected_channels_hz(sham=True) == (250.0, 250.0)
    assert p.duration_s == 1200.0                      # 20 minutos por sessão
    assert (p.sample_rate, p.bit_depth) == (48000, 16)  # sem perdas
    assert (p.fade_in_s, p.fade_out_s) == (30.0, 60.0)  # rampas assimétricas


def test_dose_total_do_estudo():
    """20 sessões de 20 min = 400 min ≈ 6 h 40 — a exposição declarada ao CEP."""
    p = _pilot()
    total_s = 20 * p.duration_s
    assert total_s == 24000.0
    assert round(total_s / 3600, 2) == 6.67


def test_bateria_fft_aprova_ativo_e_sham():
    p = _pilot()
    for sham in (False, True):
        rep = bi.validate_protocol(p, sham=sham)
        assert rep["passed"], [c for c in rep["checks"] if not c["ok"]]


def test_energia_equalizada_entre_bracos():
    """Sem isto o braço ativo poderia soar diferente do controle e o cegamento cairia."""
    assert bi.validate_arm_energy_match(_pilot())["ok"]


def test_sham_nao_tem_pista_interaural():
    """No controle os dois canais são o MESMO sinal, amostra a amostra."""
    seg = bi.synthesize_segment(_pilot(), sham=True, start_s=600.0, duration_s=1.0)
    assert np.array_equal(seg[:, 0], seg[:, 1])

    ativo = bi.synthesize_segment(_pilot(), sham=False, start_s=600.0, duration_s=1.0)
    assert not np.array_equal(ativo[:, 0], ativo[:, 1])
    # o canal esquerdo é idêntico nos dois braços: a diferença é SÓ o canal direito
    assert np.array_equal(seg[:, 0], ativo[:, 0])


def test_trecho_e_bit_a_bit_igual_ao_sinal_inteiro():
    """Validar por trechos não pode mudar o sinal — é a mesma fórmula, só que fatiada.

    Provado num protocolo curto (o de 20 min não cabe inteiro na memória: ~920 MB)."""
    curto = bi.AudioProtocol("t-3", "1.0.0", "delta", 250.0, 3.0, duration_s=8.0,
                             fade_in_s=1.0, fade_out_s=3.0, sample_rate=48000)
    inteiro = bi.synthesize(curto, sham=False)
    fs = curto.sample_rate
    for start_s, dur_s in ((0.0, 1.5), (3.0, 2.0), (6.5, 1.5)):
        trecho = bi.synthesize_segment(curto, sham=False, start_s=start_s, duration_s=dur_s)
        ini = int(round(start_s * fs))
        assert np.array_equal(trecho, inteiro[ini:ini + trecho.shape[0]])


def test_rampas_assimetricas_tem_a_duracao_pedida():
    """A rampa de entrada dura 30 s e a de saída 60 s — e o meio fica em regime permanente.

    O envelope é medido nos TONS (``with_bed=False``), contra ``tone_amplitude``: desde o leito
    ambiente (ADR-109), a amplitude plena dos tons não é mais o teto digital — é o teto menos a
    folga que o pico do leito ocupa. Medir a mistura contra o teto confundiria duas coisas
    diferentes, a forma do envelope e o quanto os tons cederam."""
    p = _pilot()
    amp = bi.tone_amplitude(p)
    assert amp < 10.0 ** (p.target_peak_dbfs / 20.0)      # os tons cederam a folga do leito

    def tons(start_s):
        return np.max(np.abs(bi.synthesize_segment(
            p, sham=False, start_s=start_s, duration_s=0.05, with_bed=False)))

    # ~metade da rampa de entrada (15 s) → envelope ≈ 0,5 (raised-cosine)
    assert 0.3 * amp < tons(15.0) < 0.7 * amp
    # logo após o fim da rampa de entrada → amplitude plena
    assert tons(31.0) > 0.99 * amp
    # ~metade da rampa de saída (30 s antes do fim) → envelope ≈ 0,5
    assert 0.3 * amp < tons(1170.0) < 0.7 * amp
    # ainda em regime permanente 61 s antes do fim (a rampa de saída só começa em 1140 s)
    assert tons(1138.0) > 0.99 * amp

    # E o que o participante de fato ouve continua abaixo do teto digital, com leito e tudo.
    mistura = bi.synthesize_segment(p, sham=False, start_s=31.0, duration_s=0.05)
    assert np.max(np.abs(mistura)) <= 10.0 ** (p.target_peak_dbfs / 20.0)


# ------------------------------------------------------------------ leito ambiente (ADR-109)
def _com_leito(**mudanças):
    """Um protocolo CURTO com leito — a fórmula é a mesma; 20 min só deixariam o teste lento."""
    base = dict(duration_s=6.0, fade_in_s=0.5, fade_out_s=0.5, sample_rate=48000,
                bit_depth=16, bed_level_dbr=bi.BED_LEVEL_DBR)
    base.update(mudanças)
    return bi.AudioProtocol("t-leito", "1.0.0", "delta", 250.0, 3.0, **base)


def test_o_protocolo_do_piloto_tem_leito_ambiente():
    """O protocolo promete a trilha de fundo; até o ADR-109 o estímulo era só os dois tons."""
    p = _pilot()
    assert p.bed_level_dbr == bi.BED_LEVEL_DBR
    assert p.bed_level_dbr <= -20.0          # "de baixa intensidade", e longe de mascarar


def test_o_gate_aprova_o_leito_do_piloto():
    rel = bi.validate_signal(bi.synthesize(_com_leito()), _com_leito(), sham=False)
    itens = {c["check"]: c["ok"] for c in rel["checks"]}
    # Os quatro itens que o leito trouxe existem de fato neste relatório...
    for nome in ("leito diótico (L == R)", "nível do leito", "leito fora da banda do estímulo"):
        assert nome in itens, f"o gate perdeu o item {nome!r}"
    assert bi.validate_bed_identical_across_arms(_com_leito())["ok"]
    assert rel["passed"]


def test_um_leito_ALTO_DEMAIS_reprova_o_gate():
    """O item de nível tem dentes: um leito na ordem de grandeza errada não passa.

    Sem isto, "nível do leito" seria um item decorativo — e o que ele protege é a diferença
    entre uma trilha de fundo e um mascaramento, que é o que o protocolo recusa."""
    alto = _com_leito(bed_level_dbr=-3.0)          # -3 dBr: quase o nível do próprio estímulo
    # Sinal com o leito ALTO, conferido contra o protocolo que declara -30 dBr.
    rel = bi.validate_signal(bi.synthesize(alto), _com_leito(), sham=False)
    itens = {c["check"]: c["ok"] for c in rel["checks"]}
    assert itens["nível do leito"] is False        # e reprova POR ISSO, não de raspão
    assert not rel["passed"]


def test_um_leito_NA_BANDA_DO_ESTIMULO_reprova_o_gate():
    """O item que torna verificável a recusa ao mascaramento também tem dentes.

    Aqui as parciais do leito são movidas para cima da portadora. É a falha que mais importa
    pegar: um leito assim mascara o estímulo, e nenhum outro item do gate perceberia."""
    original = bi.BED_PARTIALS_HZ
    bi.BED_PARTIALS_HZ = (248.0, 251.0, 254.0, 257.0)      # em cima de 250/253 Hz
    try:
        p = _com_leito()
        rel = bi.validate_signal(bi.synthesize(p), p, sham=False)
        itens = {c["check"]: c["ok"] for c in rel["checks"]}
        assert itens["leito fora da banda do estímulo"] is False
        assert not rel["passed"]
    finally:
        bi.BED_PARTIALS_HZ = original


def test_sem_leito_o_gate_nao_inventa_itens():
    """Protocolo sem leito (demo) não ganha itens que não se aplicam — nem falha por isso."""
    sem = _com_leito(bed_level_dbr=None)
    rel = bi.validate_signal(bi.synthesize(sem), sem, sham=False)
    itens = {c["check"] for c in rel["checks"]}
    assert "leito diótico (L == R)" not in itens
    assert rel["passed"]
