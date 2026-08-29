"""
tests/test_alerts.py — Alertas automáticos sobre sintomas operacionais (F4.6/ADR-093).

Prova o "Pronto (DoD)":
  (1) o alerta dispara no LIMIAR, não antes;
  (2) o *cooldown* impede tempestade (o sintoma continua, o aviso não se repete);
  (3) a janela é fixa: ocorrências velhas não somam com as novas;
  (4) falha de entrega de e-mail alimenta o detector — mas a falha do PRÓPRIO alerta não
      (senão SMTP fora viraria laço infinito);
  (5) o corpo do alerta não carrega PII, código nem braço;
  (6) sem `TEAM_NOTIFY_EMAIL` o alerta ainda conta e loga (o log é o canal);
  (7) `ALERTS_ENABLED=0` desliga; regra desconhecida é no-op; `record` nunca propaga;
  (8) o middleware traduz 5xx/401/leitura de pesquisa nos sintomas certos.
"""
from __future__ import annotations

from app.core import alerts, metrics
from app.core.email import (EmailMessage, InlineDelivery, MemoryEmailSender,
                            set_email_sender)


def _alert_metric(rule: str) -> float:
    return metrics.ALERTS.labels(rule=rule)._value.get()


class _BoomSender:
    def send(self, msg: EmailMessage) -> None:
        raise RuntimeError("smtp down")


def _arm(monkeypatch, rule: str, *, threshold: int, window_s: int = 900,
         cooldown_s: int = 3600, to: str | None = "equipe@uninta.edu.br"):
    """Configura uma regra por ambiente e devolve a caixa de saída observada."""
    up = rule.upper()
    monkeypatch.setenv(f"ALERT_{up}_THRESHOLD", str(threshold))
    monkeypatch.setenv(f"ALERT_{up}_WINDOW_S", str(window_s))
    monkeypatch.setenv(f"ALERT_{up}_COOLDOWN_S", str(cooldown_s))
    if to:
        monkeypatch.setenv("TEAM_NOTIFY_EMAIL", to)
    else:
        monkeypatch.delenv("TEAM_NOTIFY_EMAIL", raising=False)
    alerts.reset()
    fake = MemoryEmailSender()
    set_email_sender(fake)
    return fake


def test_dispara_no_limiar_e_nao_antes(monkeypatch):
    caixa = _arm(monkeypatch, "server_error", threshold=3)
    antes = _alert_metric("server_error")
    alerts.record("server_error")
    alerts.record("server_error")
    assert caixa.outbox == [] and _alert_metric("server_error") == antes   # 2 de 3: silêncio
    alerts.record("server_error")
    assert _alert_metric("server_error") == antes + 1
    assert len(caixa.outbox) == 1
    msg = caixa.outbox[0]
    assert msg.to == "equipe@uninta.edu.br" and "[Sereno]" in msg.subject
    assert msg.alert is True                       # marcado: não realimenta o detector


def test_cooldown_evita_tempestade(monkeypatch):
    caixa = _arm(monkeypatch, "server_error", threshold=2, cooldown_s=3600)
    for _ in range(20):                            # sintoma continua acontecendo
        alerts.record("server_error")
    assert len(caixa.outbox) == 1                  # um aviso, não vinte


def test_janela_fixa_nao_soma_ocorrencia_velha(monkeypatch):
    caixa = _arm(monkeypatch, "auth_failure", threshold=3, window_s=300)
    relogio = {"t": 1000.0}
    monkeypatch.setattr(alerts.time, "monotonic", lambda: relogio["t"])
    alerts.record("auth_failure")
    alerts.record("auth_failure")
    relogio["t"] += 301                            # janela virou
    alerts.record("auth_failure")
    alerts.record("auth_failure")
    assert caixa.outbox == []                      # 2 antigas + 2 novas ≠ 4 na mesma janela
    alerts.record("auth_failure")
    assert len(caixa.outbox) == 1                  # 3 na janela corrente: dispara


def test_falha_de_email_alimenta_o_detector(monkeypatch):
    _arm(monkeypatch, "email_failure", threshold=2)
    set_email_sender(_BoomSender())                # todo envio falha
    antes = _alert_metric("email_failure")
    InlineDelivery().deliver(EmailMessage(to="a@x.com", subject="s", body="c"))
    assert _alert_metric("email_failure") == antes
    InlineDelivery().deliver(EmailMessage(to="b@x.com", subject="s", body="c"))
    assert _alert_metric("email_failure") == antes + 1


def test_alerta_que_falha_nao_realimenta_o_detector(monkeypatch):
    # O cenário perigoso: SMTP fora → alerta de e-mail → alerta enviado por e-mail → falha…
    _arm(monkeypatch, "email_failure", threshold=1)
    set_email_sender(_BoomSender())
    antes = _alert_metric("email_failure")
    InlineDelivery().deliver(EmailMessage(to="c@x.com", subject="s", body="c"))
    disparos = _alert_metric("email_failure") - antes
    assert disparos == 1                           # exatamente um; sem laço


def test_corpo_do_alerta_nao_carrega_pii_nem_codigo(monkeypatch):
    _arm(monkeypatch, "email_failure", threshold=1)
    set_email_sender(_BoomSender())
    # A mensagem que falhou tem endereço e código; o ALERTA não pode repeti-los.
    InlineDelivery().deliver(EmailMessage(to="participante.fulano@hospital.br",
                                          subject="Seu código", body="codigo 998877"))
    # O provedor está quebrado, então o alerta não chega à caixa — inspeciona-se o que seria
    # enviado reconstruindo pelo mesmo caminho, com um provedor que funciona.
    caixa = MemoryEmailSender(); set_email_sender(caixa)
    alerts.reset()
    alerts.record("email_failure")
    corpo = caixa.outbox[0].body
    assert "participante.fulano" not in corpo and "998877" not in corpo
    assert "hospital.br" not in corpo
    assert "email_failure" in corpo                # regra e próxima ação, só isso
    assert "não contém dados de participante" in corpo


def test_sem_destino_conta_e_nao_envia(monkeypatch):
    caixa = _arm(monkeypatch, "server_error", threshold=1, to=None)
    antes = _alert_metric("server_error")
    alerts.record("server_error")
    assert _alert_metric("server_error") == antes + 1   # detectou
    assert caixa.outbox == []                           # mas não tinha para quem mandar


def test_desligavel_e_tolerante(monkeypatch):
    caixa = _arm(monkeypatch, "server_error", threshold=1)
    monkeypatch.setenv("ALERTS_ENABLED", "0")
    alerts.record("server_error")
    assert caixa.outbox == []
    monkeypatch.setenv("ALERTS_ENABLED", "1")
    alerts.record("regra-que-nao-existe")               # no-op, não levanta
    assert caixa.outbox == []


def test_record_nunca_propaga(monkeypatch):
    _arm(monkeypatch, "server_error", threshold=1)

    def _explode(*_a, **_k):
        raise RuntimeError("sink quebrado")

    monkeypatch.setattr(alerts, "_fire", _explode)
    alerts.record("server_error")                       # engolido: nada de derrubar o request


def test_middleware_traduz_status_no_sintoma_certo(monkeypatch):
    vistos: list[str] = []
    monkeypatch.setattr(alerts, "record", lambda rule, **_k: vistos.append(rule))
    alerts.observe_response(path_template="/sessions", status=500)
    alerts.observe_response(path_template="/auth/participant/verify-otp", status=401)
    alerts.observe_response(path_template="/research/export", status=200)
    alerts.observe_response(path_template="/audit", status=200)
    alerts.observe_response(path_template="/health", status=200)      # ruído: não conta
    alerts.observe_response(path_template="/sessions", status=404)    # nem 4xx comum
    assert vistos == ["server_error", "auth_failure", "research_access", "research_access"]


def test_401_real_pela_api_conta_como_sintoma(api, monkeypatch):
    caixa = _arm(monkeypatch, "auth_failure", threshold=2)
    client, _ = api
    client.get("/v1/research/participants")            # sem token → 401
    assert caixa.outbox == []
    client.get("/v1/research/participants")
    assert len(caixa.outbox) == 1                      # o middleware alimentou o detector
