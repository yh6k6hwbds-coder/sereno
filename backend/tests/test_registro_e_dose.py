"""
tests/test_registro_e_dose.py — Registro por sessão (G10) e dose auditiva (G9).

O protocolo aprovado tem dois parágrafos que o sistema ainda não cumpria por inteiro.

**"Registro e monitoramento"** enumera o que a plataforma registrará para CADA sessão:
horário de início e término, tempo efetivo, **interrupções e sua duração**, **volume médio e
máximo**, resultado da verificação de fones e **um item único de percepção de relaxamento de
0 a 10**. Três desses itens não tinham onde ser guardados — só a *contagem* de interrupções
era gravada, o volume aparecia apenas como o ganho declarado no início, e o relaxamento só
existia dentro do questionário pós-sessão, que é opcional e usa escala de 0 a 4.

**"Intensidade e segurança auditiva"** promete "contabilização de dose acumulada" e "alerta
ao atingir 50% do limite de referência" — 80 dB(A) por 40 h semanais (OMS/UIT, 2019).

Provamos: que o registro chega e é validado (inclusive o teto de volume no que foi
REPRODUZIDO, não só no que foi declarado); que a conta de dose é a da troca de 3 dB e
reproduz o número que o próprio protocolo afirma (6h40 de exposição fica muito abaixo da
referência); que o alerta dispara na metade; e que, sem calibração, a resposta se declara
previsão em vez de posar de medida.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.core import auth, hearing
from app.core.models import (Allocation, AudioProtocol, Participant,
                             Session as SessionModel)
from app.core.protocol import PRESCRIBED_SESSIONS
from tests.helpers import GANHO, start_body

START = "/v1/sessions"
STATUS = "/v1/participants/me/status"
AGORA = dt.datetime.now(dt.timezone.utc)


def _hdr(pid):
    return {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _protocolos(s):
    if s.query(AudioProtocol).count() == 0:
        s.add(AudioProtocol(protocol_id="rg-01", version="1.0.0", band="delta",
                            carrier_hz=250.0, beat_hz=3.0, duration_s=2.0,
                            target_peak_dbfs=-12.0, content_hash="e" * 64))
        s.add(AudioProtocol(protocol_id="rg-02", version="1.0.0", band="delta",
                            carrier_hz=250.0, beat_hz=0.0, duration_s=2.0,
                            target_peak_dbfs=-12.0, content_hash="f" * 64))


def _seed(TestSession, code="RG01", arm="A"):
    with TestSession() as s:
        _protocolos(s)
        p = Participant(study_code=code)
        s.add(p)
        s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="ref",
                         allocated_at=AGORA - dt.timedelta(days=1)))
        s.commit()
        return p.id


def _sessoes(TestSession, pid, *, quantas, segundos, dias_atras=0, ganho=None):
    """Grava sessões já encerradas, com tempo efetivo — o insumo da dose."""
    with TestSession() as s:
        proto = s.query(AudioProtocol).first()
        quando = AGORA - dt.timedelta(days=dias_atras)
        for _ in range(quantas):
            s.add(SessionModel(
                participant_id=pid, protocol_uuid=proto.id, protocol_hash=proto.content_hash,
                started_at=quando, ended_at=quando, effective_seconds=segundos,
                headphones_ok=True, completed=True, audio_gain=GANHO, gain_mean=ganho))
        s.commit()


# ------------------------------------------------------- G10: o registro por sessão
def test_a_sessao_guarda_os_itens_que_o_protocolo_lista(api):
    client, TestSession = api
    pid = _seed(TestSession, "RG-A")
    sid = client.post(START, headers=_hdr(pid), json=start_body()).json()["session_id"]
    r = client.post(f"{START}/{sid}/complete", headers=_hdr(pid), json={
        "effective_seconds": 1200, "interruptions": 2, "paused_seconds": 95,
        "gain_mean": 0.75, "gain_peak": 0.8, "relaxation_0_10": 7})
    assert r.status_code == 200, r.text
    with TestSession() as s:
        gravada = s.query(SessionModel).one()
        assert gravada.interruptions == 2 and gravada.paused_seconds == 95
        assert float(gravada.gain_mean) == 0.75 and float(gravada.gain_peak) == 0.8
        assert gravada.relaxation_0_10 == 7
        # Início e término, tempo efetivo e fones já existiam — o parágrafo pede os seis.
        assert gravada.started_at and gravada.ended_at
        assert gravada.effective_seconds == 1200 and gravada.headphones_ok is True


def test_cliente_antigo_continua_encerrando_a_sessao(api):
    """A telemetria pode voltar da fila offline gravada antes desta versão."""
    client, TestSession = api
    pid = _seed(TestSession, "RG-B")
    sid = client.post(START, headers=_hdr(pid), json=start_body()).json()["session_id"]
    r = client.post(f"{START}/{sid}/complete", headers=_hdr(pid),
                    json={"effective_seconds": 1200, "interruptions": 0})
    assert r.status_code == 200, r.text
    with TestSession() as s:
        gravada = s.query(SessionModel).one()
        # Ausência é informação: nulo, não zero — zero diria "ninguém pausou".
        assert gravada.paused_seconds is None and gravada.gain_mean is None
        assert gravada.relaxation_0_10 is None
        assert gravada.completed is True     # a adesão, que é desfecho primário, não se perde


def test_o_teto_de_volume_vale_para_o_que_foi_reproduzido(api):
    """Declarar 0,8 no início e reproduzir acima do teto no meio não pode passar."""
    client, TestSession = api
    pid = _seed(TestSession, "RG-C")
    sid = client.post(START, headers=_hdr(pid), json=start_body()).json()["session_id"]
    r = client.post(f"{START}/{sid}/complete", headers=_hdr(pid), json={
        "effective_seconds": 1200, "gain_mean": 0.8, "gain_peak": 1.5})
    assert r.status_code == 422, r.text


def test_media_maior_que_o_maximo_e_recusada(api):
    client, TestSession = api
    pid = _seed(TestSession, "RG-D")
    sid = client.post(START, headers=_hdr(pid), json=start_body()).json()["session_id"]
    r = client.post(f"{START}/{sid}/complete", headers=_hdr(pid), json={
        "effective_seconds": 1200, "gain_mean": 0.9, "gain_peak": 0.5})
    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("valor", [-1, 11])
def test_relaxamento_fora_da_escala_de_0_a_10(api, valor):
    client, TestSession = api
    pid = _seed(TestSession, f"RG-E{valor}")
    sid = client.post(START, headers=_hdr(pid), json=start_body()).json()["session_id"]
    r = client.post(f"{START}/{sid}/complete", headers=_hdr(pid),
                    json={"effective_seconds": 1200, "relaxation_0_10": valor})
    assert r.status_code == 422


def test_reenvio_sem_o_item_nao_apaga_a_resposta_ja_dada(api):
    client, TestSession = api
    pid = _seed(TestSession, "RG-F")
    sid = client.post(START, headers=_hdr(pid), json=start_body()).json()["session_id"]
    client.post(f"{START}/{sid}/complete", headers=_hdr(pid),
                json={"effective_seconds": 1200, "relaxation_0_10": 9})
    client.post(f"{START}/{sid}/complete", headers=_hdr(pid),
                json={"effective_seconds": 1200})
    with TestSession() as s:
        assert s.query(SessionModel).one().relaxation_0_10 == 9


# ------------------------------------------------------- G9: a conta da dose
def test_a_referencia_e_a_da_troca_de_3_db():
    assert hearing.allowed_hours(hearing.REFERENCE_SPL_DBA) == pytest.approx(40.0)
    # A troca "de 3 dB" é o nome arredondado: a metade exata cai em 3,0103 dB.
    assert hearing.allowed_hours(80.0 + hearing.EXCHANGE_RATE_DB) == pytest.approx(20.0)
    assert hearing.allowed_hours(80.0 - hearing.EXCHANGE_RATE_DB) == pytest.approx(80.0)
    assert hearing.EXCHANGE_RATE_DB == pytest.approx(3.01, abs=0.005)
    # A permissão semanal do adulto, na unidade da UIT-T H.870.
    assert hearing.WEEKLY_ALLOWANCE_PA2H == pytest.approx(1.6, rel=1e-6)


def test_a_exposicao_do_protocolo_fica_muito_abaixo_da_referencia():
    """O próprio protocolo afirma isso; aqui o número deixa de ser afirmação e vira conta."""
    horas = PRESCRIBED_SESSIONS * 20 / 60                 # 20 sessões de 20 min = 6h40
    assert horas == pytest.approx(6 + 40 / 60)
    fracao = hearing.dose_fraction(hearing.PROTOCOL_TARGET_SPL_DBA, horas)
    assert fracao < 0.01                                   # menos de 1% da permissão semanal
    assert hearing.allowed_hours(hearing.PROTOCOL_TARGET_SPL_DBA) == pytest.approx(4000.0)


def test_ganho_vira_nivel_por_20_log10():
    # Metade da amplitude é -6 dB, não -3: ganho é razão de amplitude.
    assert hearing.spl_for_gain(0.5, 66.0) == pytest.approx(60.0, abs=0.1)
    assert hearing.spl_for_gain(1.0, 60.0) == pytest.approx(60.0)


def test_a_dose_aparece_no_status_do_participante(api):
    client, TestSession = api
    pid = _seed(TestSession, "RG-G")
    _sessoes(TestSession, pid, quantas=5, segundos=1200)     # 5 sessões de 20 min = 1h40
    corpo = client.get(STATUS, headers=_hdr(pid)).json()["hearing"]
    assert corpo["week_hours"] == pytest.approx(5 * 1200 / 3600, abs=1e-3)
    assert corpo["total_hours"] == pytest.approx(corpo["week_hours"])
    assert corpo["alert"] is False and corpo["alert_at_pct"] == 50.0
    assert corpo["reference_spl_dba"] == 80.0 and corpo["reference_hours_per_week"] == 40.0


def test_sem_calibracao_a_dose_se_declara_previsao(api):
    """Enquanto a etapa (i) não mede o transdutor, o nível é o PRESCRITO — e a tela diz isso."""
    client, TestSession = api
    pid = _seed(TestSession, "RG-H")
    _sessoes(TestSession, pid, quantas=1, segundos=1200)
    corpo = client.get(STATUS, headers=_hdr(pid)).json()["hearing"]
    assert corpo["calibrated"] is False
    assert corpo["assumed_spl_dba"] == hearing.PROTOCOL_TARGET_SPL_DBA


def test_com_calibracao_o_ganho_passa_a_mandar(api, monkeypatch):
    client, TestSession = api
    pid = _seed(TestSession, "RG-I")
    # Nível medido em acoplador com ganho 1,0; a sessão rodou com ganho médio 0,5 (-6 dB).
    monkeypatch.setenv("AUDIO_CALIBRATED_SPL_DBA", "86")
    _sessoes(TestSession, pid, quantas=1, segundos=3600, ganho=0.5)
    corpo = client.get(STATUS, headers=_hdr(pid)).json()["hearing"]
    assert corpo["calibrated"] is True and corpo["assumed_spl_dba"] is None
    # 86 dB(A) em fundo de escala, com ganho 0,5, dá 80 dB(A) — a própria referência:
    # 1 h de 40 h permitidas = 2,5%.
    assert corpo["week_pct"] == pytest.approx(2.5, abs=0.05)


def test_o_alerta_dispara_na_metade_da_referencia(api, monkeypatch):
    client, TestSession = api
    pid = _seed(TestSession, "RG-J")
    monkeypatch.setenv("AUDIO_CALIBRATED_SPL_DBA", "80")
    # 20 h em 80 dB(A) = metade das 40 h de permissão semanal.
    _sessoes(TestSession, pid, quantas=20, segundos=3600, ganho=1.0)
    corpo = client.get(STATUS, headers=_hdr(pid)).json()["hearing"]
    assert corpo["week_pct"] == pytest.approx(50.0, abs=0.05)
    assert corpo["alert"] is True


def test_a_janela_do_alerta_e_semanal(api, monkeypatch):
    """A permissão da OMS/UIT é POR SEMANA: exposição de um mês atrás não a consome hoje."""
    client, TestSession = api
    pid = _seed(TestSession, "RG-K")
    monkeypatch.setenv("AUDIO_CALIBRATED_SPL_DBA", "80")
    _sessoes(TestSession, pid, quantas=20, segundos=3600, ganho=1.0, dias_atras=30)
    corpo = client.get(STATUS, headers=_hdr(pid)).json()["hearing"]
    assert corpo["week_hours"] == 0.0 and corpo["alert"] is False
    assert corpo["total_hours"] == pytest.approx(20.0)     # a dose acumulada não se apaga
    assert corpo["total_pct"] == pytest.approx(50.0, abs=0.05)


def test_sessao_aberta_nao_conta_dose(api):
    """Sem tempo efetivo não houve exposição medida — nem para mais, nem para menos."""
    client, TestSession = api
    pid = _seed(TestSession, "RG-L")
    client.post(START, headers=_hdr(pid), json=start_body())
    corpo = client.get(STATUS, headers=_hdr(pid)).json()["hearing"]
    assert corpo["total_hours"] == 0.0 and corpo["total_pct"] == 0.0


def test_a_dose_nao_revela_o_braco(api):
    """Mesma energia acústica nos dois braços (inegociável #1): a tela é idêntica."""
    client, TestSession = api
    corpos = []
    for code, arm in (("RG-M", "A"), ("RG-N", "B")):
        pid = _seed(TestSession, code, arm=arm)
        _sessoes(TestSession, pid, quantas=3, segundos=1200)
        corpos.append(client.get(STATUS, headers=_hdr(pid)).json()["hearing"])
    assert corpos[0] == corpos[1]
