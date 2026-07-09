"""
core/email.py — Envio de e-mail atrás de uma interface (troca de provedor + testabilidade).

Usado para entregar o OTP ao participante e alertar a equipe em eventos adversos. A
implementação concreta é escolhida por ambiente:
  - ``SMTP_HOST`` definido        → ``SmtpEmailSender`` (produção; com retries).
  - ``EMAIL_DEV_CONSOLE`` truthy  → ``ConsoleEmailSender`` (dev; imprime — NUNCA em produção).
  - caso contrário                → ``NullEmailSender`` (não envia; avisa SEM o código/corpo).

Segurança: o código OTP vai apenas no CORPO enviado; **nunca é logado**. Em falha de
configuração, o padrão seguro é não enviar (Null), evitando vazar o código no console.
Nota: o envio síncrono aqui é best-effort com retries; a fila assíncrona (RQ/Redis, ADR-031)
é o caminho de produção para desacoplar latência/falha — trocável atrás desta porta.
"""
from __future__ import annotations
import logging
import os
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage as _MimeMessage
from typing import Protocol

from app.core.config import env_truthy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


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
                       msg.to, msg.subject)


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
                last = e
                logger.warning("Falha ao enviar e-mail para %s (tentativa %d/%d).",
                               msg.to, attempt + 1, self._retries)
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
