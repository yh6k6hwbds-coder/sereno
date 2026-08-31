"""
tests/test_progress_t2.py — Avaliação intermediária T2 e descontinuação de protocolo (G6).

O protocolo diz três coisas que o sistema não cumpria:

  - a coleta ocorre em **T0, T2 (2ª semana) e T4** — havia instrumento e tela, faltava o
    momento: nada convidava o participante na 2ª semana;
  - **adesão < 50% das sessões previstas ao final da 2ª semana** descontinua o participante;
  - quem descontinua **permanece na análise por intenção de tratar** — o que faz de
    ``discontinued`` um estado diferente de ``withdrawn``.

Provamos o calendário (a janela abre no dia 14, não antes), a regra (com a fronteira exata em
50%), o que a descontinuação faz (a exposição para, o ITT não) e o que ela NÃO pode fazer
(rebaixar quem já saiu por segurança, ou repetir).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select

from app.core import auth
from app.core.models import (Allocation, AdverseEvent, AudioProtocol, Participant,
                             ProtocolDiscontinuation, SafetyAssessment, Session as SessionModel,
                             StaffUser)
from app.core.protocol import (MIN_WEEK2_ADHERENCE_PCT, PRESCRIBED_SESSIONS, T2_OPENS_DAY,
                               study_day, study_week, t2_window)
from app.modules.progress import service as progress
from tests.helpers import start_body

STATUS = "/v1/participants/me/status"
SWEEP = "/v1/discontinuations/evaluate"
LISTA = "/v1/discontinuations"

# Relógio de referência: os testes que passam por HTTP usam o relógio real do servidor, então
# o marco tem de ser "agora" e não uma data fixa (senão a janela do T2 cai no dia errado).
AGORA = dt.datetime.now(dt.timezone.utc)


def _hdr(pid):
    return {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _staff(TestSession, role="researcher"):
    with TestSession() as s:
        u = StaffUser(email=f"{uuid.uuid4().hex[:8]}@uninta.edu.br",
                      password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _alocado(TestSession, code="PG01", *, dias_atras=0, sessoes_concluidas=0,
             sessoes_parciais=0, com_protocolo=False):
    """Participante alocado há ``dias_atras`` dias, com N sessões que contam para a adesão."""
    alocado_em = AGORA - dt.timedelta(days=dias_atras)
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded="A", block=1,
                         sequence_seed_ref="ref", allocated_at=alocado_em))
        proto = s.query(AudioProtocol).filter(AudioProtocol.beat_hz > 0).first()
        if com_protocolo and proto is None:
            proto = AudioProtocol(protocol_id="pg-01", version="1.0.0", band="delta",
                                  carrier_hz=250.0, beat_hz=3.0, duration_s=2.0,
                                  target_peak_dbfs=-12.0, content_hash="a" * 64)
            s.add(proto)
            s.add(AudioProtocol(protocol_id="pg-02", version="1.0.0", band="delta",
                                carrier_hz=250.0, beat_hz=0.0, duration_s=2.0,
                                target_peak_dbfs=-12.0, content_hash="b" * 64))
            s.flush()
        if proto is not None:
            for i in range(sessoes_concluidas + sessoes_parciais):
                s.add(SessionModel(
                    participant_id=p.id, protocol_uuid=proto.id, protocol_hash=proto.content_hash,
                    started_at=alocado_em + dt.timedelta(days=i),
                    headphones_ok=True, completed=i < sessoes_concluidas))
        s.commit()
        return p.id


# --------------------------------------------------------------------- o calendário
def test_o_calendario_conta_a_partir_da_alocacao():
    alocado = AGORA - dt.timedelta(days=13)
    assert study_day(alocado, AGORA) == 14 and study_week(alocado, AGORA) == 2
    abre, fecha = t2_window(alocado)
    assert abre == alocado + dt.timedelta(days=T2_OPENS_DAY)     # dia 14, fim da 2ª semana
    assert (fecha - abre).days == 7


def test_t2_nao_esta_aberta_antes_do_fim_da_segunda_semana(api):
    client, TestSession = api
    pid = _alocado(TestSession, "PG-T2A", dias_atras=6, sessoes_concluidas=5, com_protocolo=True)
    corpo = client.get(STATUS, headers=_hdr(pid)).json()
    assert corpo["study_week"] == 1
    assert corpo["t2"]["due"] is False and corpo["t2"]["completed"] is False


def test_t2_abre_no_fim_da_segunda_semana(api):
    client, TestSession = api
    pid = _alocado(TestSession, "PG-T2B", dias_atras=14, sessoes_concluidas=9,
                   com_protocolo=True)
    corpo = client.get(STATUS, headers=_hdr(pid)).json()
    assert corpo["t2"]["due"] is True and corpo["t2"]["late"] is False
    assert corpo["status"] == "active"          # adesão 90% na 2ª semana: segue no protocolo


def test_responder_a_intermediaria_fecha_o_convite(api):
    client, TestSession = api
    pid = _alocado(TestSession, "PG-T2C", dias_atras=15, sessoes_concluidas=9,
                   com_protocolo=True)
    assert client.get(STATUS, headers=_hdr(pid)).json()["t2"]["due"] is True
    r = client.post("/v1/participants/me/safety-check", headers=_hdr(pid),
                    json={"phq9_items": [0] * 9, "moment": "intermediaria"})
    assert r.status_code == 201
    corpo = client.get(STATUS, headers=_hdr(pid)).json()
    assert corpo["t2"]["completed"] is True and corpo["t2"]["due"] is False


def test_intermediaria_anterior_a_janela_nao_conta_como_t2(api):
    """Responder por conta própria na 1ª semana é bem-vindo, mas não é a avaliação da 2ª."""
    client, TestSession = api
    pid = _alocado(TestSession, "PG-T2D", dias_atras=20, sessoes_concluidas=9,
                   com_protocolo=True)
    with TestSession() as s:
        alocado = s.scalar(select(Allocation.allocated_at)
                           .where(Allocation.participant_id == pid))
        s.add(SafetyAssessment(participant_id=pid, moment="intermediaria",
                               risk_detected=False, reasons=[], score_version="1.0.0",
                               rule_version="1.0.0",
                               assessed_at=alocado + dt.timedelta(days=3)))
        s.commit()
    corpo = client.get(STATUS, headers=_hdr(pid)).json()
    assert corpo["t2"]["completed"] is False and corpo["t2"]["due"] is True


# ------------------------------------------------------- a regra de adesão da 2ª semana
def test_adesao_abaixo_de_50_descontinua_ao_fim_da_segunda_semana(api):
    client, TestSession = api
    pid = _alocado(TestSession, "PG-AD1", dias_atras=15, sessoes_concluidas=4,
                   com_protocolo=True)          # 4 de 10 previstas = 40%
    corpo = client.get(STATUS, headers=_hdr(pid)).json()
    assert corpo["status"] == "discontinued"
    assert corpo["discontinuation"] == {
        "reason": "adesao_insuficiente", "kept_in_itt": True,
        "decided_at": corpo["discontinuation"]["decided_at"]}
    with TestSession() as s:
        d = s.query(ProtocolDiscontinuation).one()
        assert (d.sessions_completed, d.sessions_prescribed, d.study_week) == (4, 10, 2)


def test_exatamente_50_por_cento_continua(api):
    """"inferior a 50%" — a fronteira fica de fora, e é onde um erro de sinal apareceria."""
    client, TestSession = api
    pid = _alocado(TestSession, "PG-AD2", dias_atras=15, sessoes_concluidas=5,
                   com_protocolo=True)
    assert MIN_WEEK2_ADHERENCE_PCT == 50.0
    assert client.get(STATUS, headers=_hdr(pid)).json()["status"] == "active"


def test_sessao_parcial_nao_salva_a_adesao(api):
    """Abrir o áudio e sair não conta: a régua de adesão é 80% da duração (ADR-100)."""
    client, TestSession = api
    pid = _alocado(TestSession, "PG-AD3", dias_atras=15, sessoes_concluidas=3,
                   sessoes_parciais=5, com_protocolo=True)
    assert client.get(STATUS, headers=_hdr(pid)).json()["status"] == "discontinued"


def test_regra_nao_roda_antes_do_prazo(api):
    client, TestSession = api
    pid = _alocado(TestSession, "PG-AD4", dias_atras=10, sessoes_concluidas=0,
                   com_protocolo=True)
    assert client.get(STATUS, headers=_hdr(pid)).json()["status"] == "active"
    with TestSession() as s:
        assert s.query(ProtocolDiscontinuation).count() == 0


def test_sessao_atrasada_nao_reescreve_a_segunda_semana(api):
    """Uma sessão iniciada no dia 20 não conta para a adesão aferida no dia 14."""
    _client, TestSession = api
    pid = _alocado(TestSession, "PG-AD5", dias_atras=25, sessoes_concluidas=0,
                   com_protocolo=True)
    with TestSession() as s:
        proto = s.query(AudioProtocol).filter(AudioProtocol.beat_hz > 0).one()
        for i in range(8):
            s.add(SessionModel(participant_id=pid, protocol_uuid=proto.id,
                               protocol_hash=proto.content_hash,
                               started_at=AGORA - dt.timedelta(days=2),
                               headphones_ok=True, completed=True))
        s.commit()
    with TestSession() as s:
        saida = progress.evaluate_week2(s, pid, AGORA)
        s.commit()
        assert saida is not None and saida.sessions_completed == 0


# ------------------------------------------------------- o que a descontinuação faz
def test_descontinuado_nao_inicia_sessao_mas_segue_no_estudo(api):
    client, TestSession = api
    pid = _alocado(TestSession, "PG-DS1", dias_atras=15, sessoes_concluidas=2,
                   com_protocolo=True)
    r = client.post("/v1/sessions", headers=_hdr(pid), json=start_body("delta"))
    assert r.status_code == 403 and "descontinuada" in r.text.lower()
    with TestSession() as s:
        # ITT: o participante e as sessões já registradas continuam onde estavam.
        assert s.get(Participant, pid).status == "discontinued"
        assert s.query(SessionModel).filter(SessionModel.participant_id == pid).count() == 2
        assert s.query(ProtocolDiscontinuation).one().kept_in_itt is True


def test_descontinuacao_nao_rebaixa_retirada_por_seguranca(api):
    """Quem já saiu por segurança (G5) não vira 'discontinued' — como o `erase` também respeita."""
    _client, TestSession = api
    pid = _alocado(TestSession, "PG-DS2", dias_atras=15, sessoes_concluidas=0,
                   com_protocolo=True)
    with TestSession() as s:
        s.get(Participant, pid).status = "removed"
        s.commit()
    with TestSession() as s:
        assert progress.evaluate_week2(s, pid, AGORA) is None
        assert s.get(Participant, pid).status == "removed"
        assert s.query(ProtocolDiscontinuation).count() == 0


def test_descontinuar_e_idempotente(api):
    _client, TestSession = api
    pid = _alocado(TestSession, "PG-DS3", dias_atras=20, sessoes_concluidas=1,
                   com_protocolo=True)
    with TestSession() as s:
        a = progress.evaluate_week2(s, pid, AGORA)
        s.commit()
        b = progress.evaluate_week2(s, pid, AGORA + dt.timedelta(days=1))
        s.commit()
        assert a is not None and b is None
        assert s.query(ProtocolDiscontinuation).count() == 1


# ------------------------------------------------------------------ staff / varredura
def test_staff_registra_pedido_do_participante(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    pid = _alocado(TestSession, "PG-ST1", dias_atras=5, sessoes_concluidas=4,
                   com_protocolo=True)
    r = client.post(f"/v1/participants/{pid}/discontinue", headers=hdr,
                    json={"reason": "solicitacao_participante"})
    assert r.status_code == 201, r.text
    assert r.json()["reason"] == "solicitacao_participante"
    assert r.json()["kept_in_itt"] is True
    assert r.json()["study_code"] == "PG-ST1"
    # Repetir é 409 — descontinuar duas vezes não quer dizer nada.
    assert client.post(f"/v1/participants/{pid}/discontinue", headers=hdr,
                       json={"reason": "solicitacao_participante"}).status_code == 409


def test_evento_adverso_de_outro_participante_e_422(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    pid = _alocado(TestSession, "PG-ST2", dias_atras=5, com_protocolo=True)
    outro = _alocado(TestSession, "PG-ST3", dias_atras=5)
    with TestSession() as s:
        ae = AdverseEvent(participant_id=outro, type="cefaleia", severity="moderate")
        s.add(ae); s.commit(); ae_id = ae.id
    r = client.post(f"/v1/participants/{pid}/discontinue", headers=hdr,
                    json={"reason": "evento_adverso", "adverse_event_id": str(ae_id)})
    assert r.status_code == 422


def test_varredura_alcanca_quem_parou_de_abrir_o_app(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    sumido = _alocado(TestSession, "PG-SW1", dias_atras=18, sessoes_concluidas=1,
                      com_protocolo=True)
    assiduo = _alocado(TestSession, "PG-SW2", dias_atras=18, sessoes_concluidas=9,
                       com_protocolo=True)
    r = client.post(SWEEP, headers=hdr)
    assert r.status_code == 200 and r.json()["discontinued"] == 1
    assert client.post(SWEEP, headers=hdr).json()["discontinued"] == 0    # idempotente
    with TestSession() as s:
        assert s.get(Participant, sumido).status == "discontinued"
        assert s.get(Participant, assiduo).status == "active"


def test_lista_para_o_cep_e_pseudonimizada_e_sem_braco(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    _alocado(TestSession, "PG-LS1", dias_atras=18, sessoes_concluidas=0, com_protocolo=True)
    client.post(SWEEP, headers=hdr)
    r = client.get(LISTA, headers=hdr)
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["study_code"] == "PG-LS1" and item["reason"] == "adesao_insuficiente"
    texto = str(r.json()).lower()
    assert "arm" not in texto and "sham" not in texto and "active_condition" not in texto


def test_status_do_participante_nao_revela_braco(api):
    client, TestSession = api
    pid = _alocado(TestSession, "PG-NB1", dias_atras=3, sessoes_concluidas=2,
                   com_protocolo=True)
    corpo = client.get(STATUS, headers=_hdr(pid)).json()
    assert corpo["sessions_prescribed"] == PRESCRIBED_SESSIONS
    texto = str(corpo).lower()
    for proibido in ("arm", "sham", "beat", "condition", "grupo"):
        assert proibido not in texto


def test_status_exige_token_de_participante(api):
    client, TestSession = api
    assert client.get(STATUS).status_code == 401
    assert client.get(STATUS, headers=_staff(TestSession)).status_code == 403


def test_participante_nao_alocado_tem_andamento_neutro(api):
    client, TestSession = api
    with TestSession() as s:
        p = Participant(study_code="PG-NA1"); s.add(p); s.commit(); pid = p.id
    corpo = client.get(STATUS, headers=_hdr(pid)).json()
    assert corpo["allocated"] is False and corpo["t2"] is None
    assert corpo["study_week"] is None and corpo["adherence_pct"] == 0.0
