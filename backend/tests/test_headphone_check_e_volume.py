"""
tests/test_headphone_check_e_volume.py — Verificação dicótica (G4) e teto de volume (G3).

O protocolo exige duas coisas antes de cada sessão que o sistema não fazia:

  (G4) o participante identifica **em qual orelha** soou um sinal de teste, e a sessão não
       é liberada em caso de falha — a condição dicótica é pré-requisito do fenômeno
       binaural, então é testada, não declarada;
  (G3) o nível é calibrado com **limite máximo imposto por software**, que o participante
       não pode ultrapassar.

Aqui provamos o lado do servidor: recusa (422) o que reprovou, recusa ganho acima do teto,
**registra a evidência** por sessão (é o que a auditoria do estudo vai conferir) e não deixa
nada disso virar pista do braço.
"""
from __future__ import annotations

from app.core.models import Participant, Allocation, AudioProtocol, Session as SessionModel
from app.core import auth
from tests.helpers import CHECK_OK, CHECK_FALHOU, GANHO, start_body

START = "/v1/sessions"


def _seed(TestSession, code="HP01", arm="A"):
    with TestSession() as s:
        if s.query(AudioProtocol).count() == 0:
            s.add(AudioProtocol(protocol_id="hp-01", version="1.0.0", band="delta",
                                carrier_hz=250.0, beat_hz=3.0, duration_s=2.0,
                                target_peak_dbfs=-12.0, content_hash="c" * 64))
            s.add(AudioProtocol(protocol_id="hp-02", version="1.0.0", band="delta",
                                carrier_hz=250.0, beat_hz=0.0, duration_s=2.0,
                                target_peak_dbfs=-12.0, content_hash="d" * 64))
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.commit()
        return p.id


def _hdr(pid):
    return {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


# --------------------------------------------------------------------------- G4
def test_verificacao_reprovada_nao_inicia_sessao(api):
    client, TestSession = api
    hdr = _hdr(_seed(TestSession))
    r = client.post(START, headers=hdr, json=start_body("delta", headphone_check=CHECK_FALHOU))
    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    with TestSession() as s:
        assert s.query(SessionModel).count() == 0      # nada foi criado


def test_uma_rodada_so_nao_basta(api):
    """Com um desafio só, quem chutasse acertaria metade das vezes."""
    client, TestSession = api
    hdr = _hdr(_seed(TestSession))
    uma = {"version": "1.0.0", "rounds": 1, "errors": 0, "ears": "L"}
    r = client.post(START, headers=hdr, json=start_body("delta", headphone_check=uma))
    assert r.status_code == 422, r.text


def test_evidencia_fica_registrada_na_sessao(api):
    client, TestSession = api
    hdr = _hdr(_seed(TestSession))
    r = client.post(START, headers=hdr, json=start_body("delta"))
    assert r.status_code == 201, r.text
    with TestSession() as s:
        row = s.query(SessionModel).one()
        assert row.headphones_ok is True                       # derivado da verificação
        assert row.headphone_check["rounds"] == CHECK_OK["rounds"]
        assert row.headphone_check["errors"] == 0
        assert row.headphone_check["ears"] == CHECK_OK["ears"]
        # Quantas tentativas foram precisas até passar — o que a auditoria quer saber quando
        # alguém refaz o teste (fone invertido, saída em mono).
        assert row.headphone_check["attempts"] == 1
        assert float(row.audio_gain) == GANHO


def test_sem_verificacao_o_pedido_e_invalido(api):
    """O campo é obrigatório: um cliente que 'esqueça' de verificar não consegue iniciar."""
    client, TestSession = api
    hdr = _hdr(_seed(TestSession))
    r = client.post(START, headers=hdr,
                    json={"protocol_handle": "delta", "audio_gain": GANHO})
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- G3
def test_ganho_acima_do_teto_e_recusado(api, monkeypatch):
    client, TestSession = api
    hdr = _hdr(_seed(TestSession))
    monkeypatch.setenv("AUDIO_MAX_GAIN", "0.5")
    r = client.post(START, headers=hdr, json=start_body("delta", audio_gain=0.9))
    assert r.status_code == 422, r.text
    r = client.post(START, headers=hdr, json=start_body("delta", audio_gain=0.5))
    assert r.status_code == 201, r.text                 # no teto, passa


def test_ganho_fora_de_0_a_1_e_recusado(api):
    client, TestSession = api
    hdr = _hdr(_seed(TestSession))
    for valor in (0.0, -0.1, 1.5):
        r = client.post(START, headers=hdr, json=start_body("delta", audio_gain=valor))
        assert r.status_code == 422, (valor, r.text)


def test_teto_padrao_permite_o_ganho_do_app(api):
    """Sem `AUDIO_MAX_GAIN` no ambiente, vale o padrão — o estudo não fica travado por config."""
    client, TestSession = api
    hdr = _hdr(_seed(TestSession))
    r = client.post(START, headers=hdr, json=start_body("delta", audio_gain=1.0))
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------- cegamento
def test_regras_sao_identicas_nos_dois_bracos(api):
    """A recusa não pode depender do braço — seria um oráculo de condição."""
    client, TestSession = api
    hdr_a = _hdr(_seed(TestSession, code="HP0A", arm="A"))
    hdr_b = _hdr(_seed(TestSession, code="HP0B", arm="B"))
    for hdr in (hdr_a, hdr_b):
        ruim = client.post(START, headers=hdr, json=start_body("delta", headphone_check=CHECK_FALHOU))
        boa = client.post(START, headers=hdr, json=start_body("delta"))
        assert ruim.status_code == 422 and boa.status_code == 201
        assert sorted(boa.json().keys()) == ["content_hash", "protocol_handle",
                                             "session_id", "started_at"]
