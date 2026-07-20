"""
tests/test_email_delivery.py — Entrega desacoplada do request (porta EmailDelivery, E?/ADR-085).

Prova o "Pronto (DoD)":
  (1) o padrão é INLINE (envia já; comportamento de dev/teste inalterado);
  (2) BackgroundDelivery entrega fora do request — a mensagem chega ao provedor após drenar o pool;
  (3) o DESFECHO é observado na métrica (sent/failed) sem PII/corpo — falha após retries deixa de
      ser silenciosa e NÃO propaga (best-effort);
  (4) um provedor que sempre falha não derruba nem a entrega inline nem a de background;
  (5) o corpo/código NUNCA aparece na métrica exposta.
"""
from __future__ import annotations

from app.core import email as email_mod
from app.core.email import (EmailMessage, MemoryEmailSender, set_email_sender,
                           InlineDelivery, BackgroundDelivery, get_email_delivery,
                           set_email_delivery)
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


def test_set_delivery_shuts_down_previous_pool():
    # Trocar a entrega drena o pool anterior (não vaza threads).
    d1 = BackgroundDelivery(workers=1)
    set_email_delivery(d1)
    set_email_delivery(None)                        # deve chamar d1.shutdown()
    assert d1._pool._shutdown is True               # executor encerrado
