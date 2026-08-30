"""
tests/test_pilot_protocol.py — A biblioteca do estudo e a régua de adesão (ADR-100).

Guarda dois grupos de decisões que vieram do PROTOCOLO, não da engenharia:

  (1) os parâmetros do estímulo semeados em produção — 250 Hz / 253 Hz (Δf = 3 Hz, delta),
      20 min, 48 kHz, 16 bits, rampas de 30 s e 60 s, energia equalizada entre os braços;
  (2) a definição de adesão — uma sessão só conta se rodou pelo menos 80% da duração
      prescrita, e quem decide isso é o servidor.

Também prova o que o cegamento exige do ``content_hash``: identidade OPACA, não derivável
dos parâmetros publicados no projeto.
"""
from __future__ import annotations

import hashlib
import numpy as np

from app.core.models import Participant, Allocation, AudioProtocol, Session as SessionModel
from app.core import auth
from app.modules.sessions import audio_render
from app.modules.research.export_service import PRESCRIBED_SESSIONS, MIN_COMPLETION_RATIO
from scripts import seed_protocols as sp
from tests.helpers import start_body


# --------------------------------------------------------------------------- (1) estímulo
def test_parametros_do_protocolo_aprovado():
    assert (sp.CARRIER_HZ, sp.BEAT_HZ, sp.BAND) == (250.0, 3.0, "delta")
    assert sp.DURATION_S == 1200.0                    # 20 minutos por sessão
    assert sp.SAMPLE_RATE == 48000
    assert (sp.FADE_IN_S, sp.FADE_OUT_S) == (30.0, 60.0)
    assert sp.TARGET_PEAK_DBFS < 0.0                  # teto digital, nunca fundo de escala


def test_dose_prescrita_bate_com_o_protocolo():
    """20 sessões de 20 min = 400 min ≈ 6 h 40 — a exposição declarada ao CEP."""
    assert PRESCRIBED_SESSIONS == 20
    assert PRESCRIBED_SESSIONS * sp.DURATION_S == 24000.0
    assert MIN_COMPLETION_RATIO == 0.8


def test_biblioteca_tem_ativo_e_controle_com_o_mesmo_resto():
    """Os dois braços diferem SÓ pela diferença interaural — é o que sustenta o cegamento."""
    beats = sorted(spec["beat_hz"] for spec in sp.LIBRARY)
    assert beats == [0.0, 3.0]
    rows = [sp._row(spec) for spec in sp.LIBRARY]
    for campo in ("band", "carrier_hz", "duration_s", "sample_rate",
                  "fade_in_s", "fade_out_s", "target_peak_dbfs", "version"):
        assert len({getattr(r, campo) for r in rows}) == 1, f"{campo} difere entre os braços"


def test_content_hash_e_opaco_e_nao_derivavel():
    """Hash derivado dos parâmetros (ou de um rótulo) permitiria descobrir o braço.

    O protocolo é público: quem tiver o projeto pode recalcular qualquer hash determinístico
    e comparar com o que o cliente recebeu."""
    a, b = sp._row(sp.LIBRARY[0]), sp._row(sp.LIBRARY[0])
    assert a.content_hash != b.content_hash            # aleatório, não função dos parâmetros
    assert len(a.content_hash) == 64
    for rotulo in (b"ativo", b"sham", b"delta-3", b"250-253"):
        assert a.content_hash != hashlib.sha256(rotulo).hexdigest()


def test_estimulo_semeado_passa_na_fft():
    """O seeder recusa gravar um protocolo que não valide — aqui a validação de fato roda."""
    for spec in sp.LIBRARY:
        sp._verify_renderable(spec)                    # levanta ValueError se reprovar


def test_render_honra_taxa_e_rampas_do_protocolo():
    """A linha do banco determina o artefato: taxa e rampas não são constantes de módulo."""
    r = audio_render.render_protocol(carrier_hz=250.0, beat_hz=3.0, duration_s=1.0,
                                     target_peak_dbfs=-12.0, sample_rate=48000,
                                     fade_in_s=0.25, fade_out_s=0.5)
    assert r.sample_rate == 48000
    # 1 s a 48 kHz, estéreo, 16 bits = 192 000 bytes de dados + cabeçalho WAV
    assert len(r.wav_bytes) > 192000

    seg = audio_render.synthesize_segment(250.0, 3.0, 1.0, -12.0, sample_rate=48000,
                                          fade_in_s=0.25, fade_out_s=0.5)
    amp = 10.0 ** (-12.0 / 20.0)
    assert np.max(np.abs(seg[:6000])) < amp           # dentro da rampa de entrada
    assert np.max(np.abs(seg[24000:24480])) > 0.99 * amp   # regime permanente


def test_sintese_em_blocos_nao_muda_um_bit():
    """A síntese em janelas (que torna os 20 min viáveis) tem de dar o MESMO WAV."""
    kw = dict(carrier_hz=250.0, beat_hz=3.0, duration_s=25.0, target_peak_dbfs=-12.0,
              sample_rate=48000, fade_in_s=1.0, fade_out_s=2.0)
    original = audio_render.CHUNK_S
    try:
        audio_render.CHUNK_S = 30.0                    # uma janela só
        inteiro = audio_render.render_protocol(**kw)
        audio_render.CHUNK_S = 2.0                     # treze janelas
        fatiado = audio_render.render_protocol(**kw)
    finally:
        audio_render.CHUNK_S = original
    assert inteiro.sha256 == fatiado.sha256


# ----------------------------------------------------------------------------- (2) adesão
DUR_TESTE = 100.0        # protocolo curto: 80% = 80 s


def _seed(TestSession):
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="pt-0001", version="1.0.0", band="delta",
                            carrier_hz=250.0, beat_hz=3.0, duration_s=DUR_TESTE,
                            target_peak_dbfs=-12.0, sample_rate=48000,
                            fade_in_s=3.0, fade_out_s=3.0,
                            content_hash="a" * 64))
        p = Participant(study_code="ADH1"); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded="A", block=1, sequence_seed_ref="ref"))
        s.commit()
        return p.id


def _sessao(client, hdr, efetivo: int):
    r = client.post("/v1/sessions", headers=hdr,
                    json=start_body("delta"))
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    return client.post(f"/v1/sessions/{sid}/complete", headers=hdr,
                       json={"effective_seconds": efetivo, "interruptions": 0})


def test_sessao_curta_nao_conta_para_adesao(api):
    client, TestSession = api
    pid = _seed(TestSession)
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}

    r = _sessao(client, hdr, 60)                       # 60% da duração
    assert r.status_code == 200, r.text
    assert r.json()["counts_for_adherence"] is False

    r = _sessao(client, hdr, 95)                       # 95% da duração
    assert r.json()["counts_for_adherence"] is True

    with TestSession() as s:
        marcadas = [x.completed for x in s.query(SessionModel).order_by(SessionModel.started_at)]
    assert marcadas == [False, True]


def test_limiar_e_exatamente_80_por_cento(api):
    client, TestSession = api
    pid = _seed(TestSession)
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    assert _sessao(client, hdr, 79).json()["counts_for_adherence"] is False
    assert _sessao(client, hdr, 80).json()["counts_for_adherence"] is True


def test_resposta_do_encerramento_nao_revela_o_braco(api):
    client, TestSession = api
    pid = _seed(TestSession)
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    corpo = _sessao(client, hdr, 90).json()
    texto = str(corpo).lower()
    for proibido in ("active", "sham", "beat", "arm", "condition", "ativo", "delta"):
        assert proibido not in texto
