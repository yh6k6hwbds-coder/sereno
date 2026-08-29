"""
core/email.py — Envio de e-mail atrás de uma interface (troca de provedor + testabilidade).

Usado para entregar o OTP ao participante e alertar a equipe em eventos adversos. A
implementação concreta é escolhida por ambiente:
  - ``SMTP_HOST`` definido        → ``SmtpEmailSender`` (produção; com retries).
  - ``EMAIL_DEV_CONSOLE`` truthy  → ``ConsoleEmailSender`` (dev; imprime — NUNCA em produção).
  - caso contrário                → ``NullEmailSender`` (não envia; avisa SEM o código/corpo).

Segurança: o código OTP vai apenas no CORPO enviado; **nunca é logado**. Em falha de
configuração, o padrão seguro é não enviar (Null), evitando vazar o código no console.
Nota: o envio síncrono aqui é best-effort com retries; a fila assíncrona (RQ/Redis, ADR-092)
é o caminho de produção para desacoplar latência/falha — trocável atrás desta porta.
"""
from __future__ import annotations
import logging
import os
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage as _MimeMessage
from typing import Protocol

from app.core.config import env_truthy

logger = logging.getLogger(__name__)


class PermanentEmailError(RuntimeError):
    """Recusa **definitiva** do provedor (bounce): caixa inexistente, domínio inválido,
    remetente barrado. Reintentar não muda o desfecho — só queima a janela do OTP e a
    reputação do remetente. Distinta da falha transitória (rede/4xx), que **é** reintentada."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str
    # `True` só para o e-mail de ALERTA (ADR-093). Uma falha ao entregar o próprio alerta
    # não pode realimentar o detector de falha de e-mail — senão SMTP fora vira laço.
    alert: bool = False


def mask_recipient(addr: str) -> str:
    """Endereço reduzido ao domínio (``***@dominio``) para log/diagnóstico.

    O endereço inteiro é PII (`CLAUDE.md`: nunca logar PII), mas o **domínio** é o que
    torna um bounce acionável (todo o domínio recusando ≠ uma caixa inexistente) e não
    identifica ninguém. Sem ``@``, some por inteiro."""
    _, sep, domain = addr.rpartition("@")
    return f"***@{domain}" if sep else "***"


def is_permanent_failure(exc: BaseException) -> bool:
    """A recusa é definitiva (5xx / destinatário inválido) e não deve ser reintentada?

    O SMTP separa 4xx (tente de novo: caixa cheia, greylisting, indisponível) de 5xx
    (não adianta: caixa inexistente, domínio inválido, remetente barrado). Erro de rede
    ou exceção sem código é tratado como **transitório** — o padrão seguro aqui é
    reintentar, porque descartar um OTP por engano deixa o participante travado."""
    if isinstance(exc, PermanentEmailError):
        return True
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        recipients = getattr(exc, "recipients", None) or {}
        # Todos recusados com 5xx → bounce. Vazio (nunca visto na prática) → transitório.
        return bool(recipients) and all(
            isinstance(code, int) and 500 <= code < 600 for code, _ in recipients.values())
    code = getattr(exc, "smtp_code", None)
    return isinstance(code, int) and 500 <= code < 600


class EmailSender(Protocol):
    def send(self, msg: EmailMessage) -> None: ...


class MemoryEmailSender:
    """Guarda as mensagens numa lista (para testes)."""
    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, msg: EmailMessage) -> None:
        self.outbox.append(msg)


class NullEmailSender:
    """Não envia nada — padrão seguro quando o e-mail não está configurado. NÃO loga o corpo."""
    def send(self, msg: EmailMessage) -> None:
        logger.warning("E-mail não configurado; mensagem para %s (%s) não enviada.",
                       mask_recipient(msg.to), msg.subject)


class ConsoleEmailSender:
    """DEV apenas: imprime a mensagem (inclui o código). Jamais habilitar em produção."""
    def send(self, msg: EmailMessage) -> None:
        print(f"[email → {msg.to}] {msg.subject}\n{msg.body}")


class SmtpEmailSender:
    """Envio real por SMTP, com retries e backoff. Não loga o corpo/código.

    Suporta os dois modos comuns de provedor: ``STARTTLS`` (porta 587, upgrade da conexão
    em claro) e ``SSL`` implícito/SMTPS (porta 465, TLS desde o handshake). Escolher errado
    trava o envio — e como o disparo do OTP é best-effort, o participante ficaria sem código
    e sem sinal; por isso o modo é explícito (ver ``_build_from_env``)."""
    def __init__(self, host: str, port: int, user: str | None, password: str | None,
                 sender: str, *, use_tls: bool = True, use_ssl: bool = False,
                 retries: int = 3) -> None:
        self._host, self._port = host, port
        self._user, self._password = user, password
        self._sender, self._use_tls, self._use_ssl = sender, use_tls, use_ssl
        self._retries = max(retries, 1)

    def send(self, msg: EmailMessage) -> None:
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                self._send_once(msg)
                return
            except Exception as e:  # noqa: BLE001 — reintenta erros transitórios de SMTP
                if is_permanent_failure(e):
                    # Bounce: o provedor recusou em definitivo. Reintentar é inútil e
                    # prejudica a reputação do remetente — para na hora (ADR-092).
                    raise PermanentEmailError(f"entrega recusada em definitivo "
                                              f"({type(e).__name__})") from e
                last = e
                logger.warning("Falha transitória ao enviar e-mail para %s (tentativa %d/%d).",
                               mask_recipient(msg.to), attempt + 1, self._retries)
                time.sleep(min(2 ** attempt, 5))
        assert last is not None
        raise last

    def _send_once(self, msg: EmailMessage) -> None:
        mime = _MimeMessage()
        mime["From"] = self._sender
        mime["To"] = msg.to
        mime["Subject"] = msg.subject
        mime.set_content(msg.body)
        if self._use_ssl:
            # SMTPS: TLS desde o handshake (não fazer STARTTLS por cima).
            with smtplib.SMTP_SSL(self._host, self._port, timeout=10) as s:
                self._deliver(s, mime)
        else:
            with smtplib.SMTP(self._host, self._port, timeout=10) as s:
                if self._use_tls:
                    s.starttls()
                self._deliver(s, mime)

    def _deliver(self, s: smtplib.SMTP, mime: _MimeMessage) -> None:
        if self._user:
            s.login(self._user, self._password or "")
        s.send_message(mime)


_sender: EmailSender | None = None


def _build_from_env() -> EmailSender:
    host = os.getenv("SMTP_HOST")
    if host:
        port = int(os.getenv("SMTP_PORT", "587"))
        # SSL implícito (SMTPS) se pedido explicitamente OU pela porta canônica 465;
        # senão, STARTTLS (587). Não misturar os dois.
        use_ssl = env_truthy(os.getenv("SMTP_USE_SSL")) or port == 465
        return SmtpEmailSender(
            host, port,
            os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"),
            os.getenv("SMTP_FROM", "no-reply@sereno.example"),
            use_tls=not use_ssl, use_ssl=use_ssl,
        )
    if os.getenv("EMAIL_DEV_CONSOLE"):
        return ConsoleEmailSender()
    return NullEmailSender()


def get_email_sender() -> EmailSender:
    global _sender
    if _sender is None:
        _sender = _build_from_env()
    return _sender


def set_email_sender(sender: EmailSender | None) -> None:
    """Injeta um provedor (testes) ou força reconstrução na próxima chamada (None)."""
    global _sender
    _sender = sender


# ---------------------------------------------------------------------------
# Entrega (porta): desacopla o ENVIO do caminho da requisição (ADR-085).
# ---------------------------------------------------------------------------
# O envio SMTP é I/O de rede com retries+timeouts: feito no thread do request, um provedor
# lento/fora bloqueia `request-otp` (público, alvo de abuso) e o relato de evento adverso (P0).
# A entrega é uma porta: `inline` (padrão — envia já; determinístico p/ dev/teste) ou
# `background` (thread pool; o request retorna na hora). Uma fila RQ/Redis é o próximo
# adaptador desta mesma porta (a "construção", ADR-031). O DESFECHO é sempre observado
# (métrica), nunca o corpo/código — assim uma falha após retries deixa de ser silenciosa.

def _send_and_observe(msg: EmailMessage, *, reraise_transient: bool = False) -> None:
    """Envia pelo provedor atual e conta o desfecho. Nunca propaga (best-effort) nem loga o corpo.

    Três desfechos, não dois (ADR-092): ``sent``, ``bounced`` (recusa definitiva — endereço
    provavelmente errado, exige ação humana) e ``failed`` (transitório, esgotou os retries).
    Separá-los é o que permite alertar em cima do sintoma certo.

    ``reraise_transient`` (só o worker da fila usa): repropaga a falha transitória para o RQ
    **reintentar mais tarde** — engolir aqui anularia a durabilidade que motiva a fila. O
    bounce nunca é repropagado: reintentar recusa definitiva não muda nada."""
    from app.core import metrics  # import tardio: evita ciclo e mantém metrics opcional
    try:
        get_email_sender().send(msg)
        metrics.observe_email("sent")
    except Exception as exc:  # noqa: BLE001 — entrega é best-effort; não derruba request/worker
        permanent = is_permanent_failure(exc)
        metrics.observe_email("bounced" if permanent else "failed")
        logger.warning("Entrega de e-mail para %s (%s) %s.", mask_recipient(msg.to), msg.subject,
                       "foi recusada em definitivo" if permanent else "falhou após retries")
        if not msg.alert:
            # Alimenta o detector (ADR-093) — exceto quando a mensagem É o alerta.
            from app.core import alerts
            alerts.record("email_failure")
        if reraise_transient and not permanent:
            raise


class EmailDelivery(Protocol):
    def deliver(self, msg: EmailMessage) -> None: ...
    def shutdown(self) -> None: ...


class InlineDelivery:
    """Envia de forma SÍNCRONA (padrão). Comportamento de dev/teste inalterado."""
    def deliver(self, msg: EmailMessage) -> None:
        _send_and_observe(msg)

    def shutdown(self) -> None:
        pass


class BackgroundDelivery:
    """Envia num thread pool: o request retorna na hora, sem esperar o SMTP (prod single-instance)."""
    def __init__(self, workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max(workers, 1),
                                        thread_name_prefix="email")

    def deliver(self, msg: EmailMessage) -> None:
        self._pool.submit(_send_and_observe, msg)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)


def send_email_job(to: str, subject: str, body: str, alert: bool = False) -> None:
    """Job executado pelo **worker** (fora do processo da API) — ver ``scripts/email_worker.py``.

    O caminho desta função é serializado na fila: renomeá-la/movê-la invalida jobs já
    enfileirados. Recebe campos soltos (não o dataclass) para não acoplar a fila ao
    formato interno da mensagem; ``alert`` viaja junto para o worker não realimentar o
    detector ao falhar entregando o próprio alerta (ADR-093)."""
    _send_and_observe(EmailMessage(to=to, subject=subject, body=body, alert=alert),
                      reraise_transient=True)


class QueueDelivery:
    """Enfileira o envio numa fila **RQ/Redis**: a entrega sobrevive a restart e deploy da API.

    Diferença para ``BackgroundDelivery`` (thread pool): ali um deploy no meio do envio perde
    a mensagem em memória — aqui o job está no Redis e um worker o retoma. É o que a porta
    ``EmailDelivery`` prometia desde o ADR-085; ADR-092 constrói.

    **Retenção do corpo:** o job carrega o corpo, e o corpo do OTP contém o código. Por isso
    o job tem TTL curto (``EMAIL_JOB_TTL``, default 10 min — a mesma ordem da validade do
    OTP), ``result_ttl=0`` e ``failure_ttl=0``: nada de OTP parado em registro de job morto.
    O desfecho continua visível na **métrica**, que não carrega corpo nem destinatário."""

    def __init__(self, queue, *, job_ttl: int = 600, retries: int = 3) -> None:
        self._q = queue
        self._job_ttl = job_ttl
        self._retries = max(retries, 1)

    def deliver(self, msg: EmailMessage) -> None:
        from rq import Retry  # import tardio: só quando a fila está em uso
        try:
            self._q.enqueue(
                send_email_job, msg.to, msg.subject, msg.body, msg.alert,
                retry=Retry(max=self._retries, interval=[10, 60, 300][:self._retries]),
                ttl=self._job_ttl,      # tempo máximo esperando na fila
                result_ttl=0,           # não guarda resultado
                failure_ttl=0,          # não guarda o job morto (com o corpo dentro)
            )
        except Exception:  # noqa: BLE001 — Redis fora não pode travar o request
            # Degrada para envio direto: melhor tentar agora do que perder o OTP calado.
            logger.warning("Fila de e-mail indisponível; entregando inline nesta mensagem.")
            _send_and_observe(msg)

    def shutdown(self) -> None:
        pass  # a fila vive no Redis; não há pool local para drenar


_delivery: EmailDelivery | None = None


def get_email_delivery() -> EmailDelivery:
    """Entrega atual. Reconstrói do ambiente (`EMAIL_DELIVERY`) — padrão `inline`.

    ``queue`` exige ``REDIS_URL``: sem ele não há fila, e cair calado para inline daria a
    falsa impressão de durabilidade — falha explícita (o startup quebra, não o participante)."""
    global _delivery
    if _delivery is None:
        mode = os.getenv("EMAIL_DELIVERY", "inline").strip().lower()
        if mode in ("queue", "rq", "redis"):
            url = os.getenv("REDIS_URL")
            if not url:
                raise RuntimeError(
                    "EMAIL_DELIVERY=queue exige REDIS_URL (a fila vive no Redis). "
                    "Sem ele, use 'background' ou 'inline'.")
            import redis                       # imports tardios: só neste modo
            from rq import Queue
            _delivery = QueueDelivery(
                Queue(os.getenv("EMAIL_QUEUE", "sereno-email"),
                      connection=redis.Redis.from_url(url)),
                job_ttl=int(os.getenv("EMAIL_JOB_TTL", "600")),
                retries=int(os.getenv("EMAIL_JOB_RETRIES", "3")),
            )
        elif mode in ("background", "async", "thread"):
            _delivery = BackgroundDelivery(int(os.getenv("EMAIL_WORKERS", "2")))
        else:
            _delivery = InlineDelivery()
    return _delivery


def set_email_delivery(delivery: EmailDelivery | None) -> None:
    """Injeta uma entrega (teste) ou força reconstrução na próxima chamada (None).

    Encerra a entrega anterior (drena o pool do BackgroundDelivery) para não vazar threads."""
    global _delivery
    if _delivery is not None and _delivery is not delivery:
        try:
            _delivery.shutdown()
        except Exception:  # noqa: BLE001 — shutdown best-effort
            pass
    _delivery = delivery
