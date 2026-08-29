"""
tests/test_email_delivery.py — Entrega desacoplada do request (porta EmailDelivery, E?/ADR-085).

Prova o "Pronto (DoD)":
  (1) o padrão é INLINE (envia já; comportamento de dev/teste inalterado);
  (2) BackgroundDelivery entrega fora do request — a mensagem chega ao provedor após drenar o pool;
  (3) o DESFECHO é observado na métrica (sent/failed) sem PII/corpo — falha após retries deixa de
      ser silenciosa e NÃO propaga (best-effort);
  (4) um provedor que sempre falha não derruba nem a entrega inline nem a de background;
  (5) o corpo/código NUNCA aparece na métrica exposta.

Fatia F4.5/ADR-092 acrescenta a entrega DURÁVEL e a distinção de bounce:
  (6) recusa definitiva (5xx) não é reintentada e conta como `bounced`, não `failed`;
  (7) falha transitória (4xx/rede) continua reintentada e conta como `failed`;
  (8) `QueueDelivery` enfileira em vez de enviar, e cai para inline se o Redis estiver fora;
  (9) o job do worker repropaga o transitório (para o RQ reintentar) e engole o bounce;
 (10) `EMAIL_DELIVERY=queue` sem `REDIS_URL` falha explícito (não finge durabilidade);
 (11) o log de falha traz só o domínio do destinatário — nunca o endereço (PII).
"""
from __future__ import annotations

import smtplib

import pytest

from app.core import email as email_mod
from app.core.email import (EmailMessage, MemoryEmailSender, set_email_sender,
                           InlineDelivery, BackgroundDelivery, get_email_delivery,
                           set_email_delivery, PermanentEmailError, QueueDelivery,
                           SmtpEmailSender, is_permanent_failure, mask_recipient,
                           send_email_job)
from app.core import metrics


def _emails_metric(outcome: str) -> float:
    return metrics.EMAILS.labels(outcome=outcome)._value.get()   # leitura direta do contador


class _BoomSender:
    """Provedor que sempre falha (simula SMTP fora)."""
    def send(self, msg: EmailMessage) -> None:
        raise RuntimeError("smtp down")


def test_default_delivery_is_inline(monkeypatch):
    monkeypatch.delenv("EMAIL_DELIVERY", raising=False)
    set_email_delivery(None)                       # reconstrói do ambiente
    assert isinstance(get_email_delivery(), InlineDelivery)


def test_background_mode_from_env(monkeypatch):
    monkeypatch.setenv("EMAIL_DELIVERY", "background")
    set_email_delivery(None)
    assert isinstance(get_email_delivery(), BackgroundDelivery)


def test_inline_delivers_synchronously_and_counts_sent():
    fake = MemoryEmailSender(); set_email_sender(fake)
    before = _emails_metric("sent")
    InlineDelivery().deliver(EmailMessage(to="a@x.com", subject="s", body="corpo 123456"))
    assert len(fake.outbox) == 1                    # já entregue, sem esperar
    assert _emails_metric("sent") == before + 1


def test_background_delivers_after_pool_drains():
    fake = MemoryEmailSender(); set_email_sender(fake)
    d = BackgroundDelivery(workers=2)
    d.deliver(EmailMessage(to="b@x.com", subject="s", body="corpo"))
    d.shutdown()                                    # drena: aguarda o worker terminar
    assert len(fake.outbox) == 1 and fake.outbox[0].to == "b@x.com"


def test_failure_is_observed_not_raised_inline():
    set_email_sender(_BoomSender())
    before = _emails_metric("failed")
    # best-effort: não propaga, mas conta a falha (deixa de ser perda silenciosa).
    InlineDelivery().deliver(EmailMessage(to="c@x.com", subject="s", body="corpo"))
    assert _emails_metric("failed") == before + 1


def test_failure_is_observed_not_raised_background():
    set_email_sender(_BoomSender())
    before = _emails_metric("failed")
    d = BackgroundDelivery(workers=1)
    d.deliver(EmailMessage(to="d@x.com", subject="s", body="corpo"))
    d.shutdown()
    assert _emails_metric("failed") == before + 1


def test_metric_exposes_no_body():
    fake = MemoryEmailSender(); set_email_sender(fake)
    InlineDelivery().deliver(EmailMessage(to="e@x.com", subject="assunto", body="segredo 999888"))
    body, _ = metrics.render()
    # Inspeciona SÓ as linhas de `emails_total` (onde um vazamento apareceria) — checar o dump
    # inteiro é frágil: um float de latência qualquer pode conter a sequência por acaso.
    email_lines = [ln for ln in body.decode().splitlines() if ln.startswith("emails_total")]
    assert email_lines                                   # a métrica existe
    blob = "\n".join(email_lines)
    # emails_total agrega só por desfecho; nunca destinatário, assunto ou código.
    assert "999888" not in blob and "e@x.com" not in blob and "assunto" not in blob
    assert all("outcome=" in ln for ln in email_lines)


# ---------------------------------------------------------------------------
# F4.5 / ADR-092 — bounce vs. falha transitória, e entrega durável (fila RQ/Redis)
# ---------------------------------------------------------------------------

class _RefusedSender:
    """Provedor que recusa em definitivo (caixa inexistente, 550)."""
    def send(self, msg: EmailMessage) -> None:
        raise smtplib.SMTPRecipientsRefused({msg.to: (550, b"mailbox unavailable")})


class _FakeQueue:
    """Fila de mentira: registra o que seria enfileirado, sem Redis."""
    def __init__(self, boom: bool = False) -> None:
        self.jobs: list[tuple] = []
        self._boom = boom

    def enqueue(self, func, *args, **kwargs):
        if self._boom:
            raise ConnectionError("redis down")
        self.jobs.append((func, args, kwargs))
        return object()


def test_classifica_5xx_como_definitivo_e_4xx_como_transitorio():
    # O SMTP separa "não adianta insistir" (5xx) de "tente de novo" (4xx).
    assert is_permanent_failure(smtplib.SMTPRecipientsRefused({"a@x.com": (550, b"no such user")}))
    assert not is_permanent_failure(
        smtplib.SMTPRecipientsRefused({"a@x.com": (451, b"greylisted")}))
    assert is_permanent_failure(smtplib.SMTPSenderRefused(553, b"bad sender", "s@x.com"))
    assert not is_permanent_failure(smtplib.SMTPResponseException(421, b"try later"))
    # Erro sem código (rede/DNS) é transitório: descartar OTP por engano trava o participante.
    assert not is_permanent_failure(ConnectionResetError("peer reset"))


def test_bounce_conta_como_bounced_e_nao_como_failed():
    set_email_sender(_RefusedSender())
    antes_b, antes_f = _emails_metric("bounced"), _emails_metric("failed")
    InlineDelivery().deliver(EmailMessage(to="ninguem@x.com", subject="s", body="corpo 123456"))
    assert _emails_metric("bounced") == antes_b + 1     # exige ação humana (endereço errado)
    assert _emails_metric("failed") == antes_f          # não polui o sintoma transitório


def test_bounce_nao_e_reintentado_pelo_smtp_sender(monkeypatch):
    # 3 retries configurados, mas 5xx deve parar na PRIMEIRA tentativa.
    tentativas = []

    def _boom(msg):
        tentativas.append(msg)
        raise smtplib.SMTPRecipientsRefused({msg.to: (550, b"no such user")})

    s = SmtpEmailSender("host", 587, None, None, "de@x.com", retries=3)
    monkeypatch.setattr(s, "_send_once", _boom)
    monkeypatch.setattr(email_mod.time, "sleep", lambda *_: None)
    with pytest.raises(PermanentEmailError):
        s.send(EmailMessage(to="ninguem@x.com", subject="s", body="c"))
    assert len(tentativas) == 1


def test_transitorio_continua_reintentando(monkeypatch):
    tentativas = []

    def _boom(msg):
        tentativas.append(msg)
        raise smtplib.SMTPResponseException(421, b"try later")

    s = SmtpEmailSender("host", 587, None, None, "de@x.com", retries=3)
    monkeypatch.setattr(s, "_send_once", _boom)
    monkeypatch.setattr(email_mod.time, "sleep", lambda *_: None)
    with pytest.raises(smtplib.SMTPResponseException):
        s.send(EmailMessage(to="alguem@x.com", subject="s", body="c"))
    assert len(tentativas) == 3                          # esgotou os retries, como antes


def test_queue_delivery_enfileira_em_vez_de_enviar():
    fake_sender = MemoryEmailSender(); set_email_sender(fake_sender)
    q = _FakeQueue()
    QueueDelivery(q, job_ttl=600, retries=3).deliver(
        EmailMessage(to="f@x.com", subject="s", body="corpo"))
    assert fake_sender.outbox == []                      # o request NÃO enviou nada
    (func, args, kwargs), = q.jobs
    assert func is send_email_job and args == ("f@x.com", "s", "corpo", False)
    # O corpo carrega o OTP: nada dele pode ficar parado no Redis depois do fim do job.
    assert kwargs["result_ttl"] == 0 and kwargs["failure_ttl"] == 0 and kwargs["ttl"] == 600


def test_queue_delivery_cai_para_inline_se_o_redis_estiver_fora():
    fake_sender = MemoryEmailSender(); set_email_sender(fake_sender)
    QueueDelivery(_FakeQueue(boom=True)).deliver(
        EmailMessage(to="g@x.com", subject="s", body="corpo"))
    # Melhor entregar agora do que perder o OTP calado por causa do Redis.
    assert len(fake_sender.outbox) == 1


def test_job_do_worker_repropaga_transitorio_e_engole_bounce():
    set_email_sender(_BoomSender())                      # falha sem código = transitória
    with pytest.raises(RuntimeError):                    # repropaga → o RQ reintenta
        send_email_job("h@x.com", "s", "corpo")
    set_email_sender(_RefusedSender())
    send_email_job("i@x.com", "s", "corpo")              # bounce: não repropaga (não adianta)


def test_modo_queue_sem_redis_url_falha_explicito(monkeypatch):
    monkeypatch.setenv("EMAIL_DELIVERY", "queue")
    monkeypatch.delenv("REDIS_URL", raising=False)
    set_email_delivery(None)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        get_email_delivery()                             # não finge durabilidade em silêncio
    set_email_delivery(None)


def test_log_de_falha_nao_traz_o_endereco_completo(caplog):
    set_email_sender(_RefusedSender())
    with caplog.at_level("WARNING"):
        InlineDelivery().deliver(
            EmailMessage(to="participante.fulano@hospital.br", subject="s", body="c"))
    texto = caplog.text
    assert "participante.fulano" not in texto            # PII fora do log (CLAUDE.md)
    assert "***@hospital.br" in texto                    # domínio basta para agir no bounce


def test_mascara_endereco_sem_arroba():
    assert mask_recipient("sem-arroba") == "***"


def test_set_delivery_shuts_down_previous_pool():
    # Trocar a entrega drena o pool anterior (não vaza threads).
    d1 = BackgroundDelivery(workers=1)
    set_email_delivery(d1)
    set_email_delivery(None)                        # deve chamar d1.shutdown()
    assert d1._pool._shutdown is True               # executor encerrado
