"""
core/alerts.py — Alertas automáticos sobre os sintomas operacionais (F4.6/ADR-093).

O ADR-080 expôs métricas e o ADR-085 passou a contar o desfecho da entrega de e-mail. Mas
métrica só vira **detecção** quando alguém olha: o `/metrics` do piloto não tem Prometheus na
frente, e o RIPD cobra detecção de **R-03** (acesso indevido por insider) e **R-06** (evento
adverso não percebido a tempo). Este módulo fecha essa lacuna sem infraestrutura nova: conta
sintomas numa janela e, ao cruzar o limiar, **avisa um humano** por e-mail e por log.

Princípios:
  - **Sem PII, sem braço, sem corpo.** O alerta carrega regra, contagem, janela e o que fazer —
    nunca quem, nem qual participante. Quem investiga vai à auditoria (que registra o ator).
  - **Não vira tempestade.** Cada regra tem *cooldown*: dispara uma vez e cala pelo período,
    mesmo que o sintoma continue.
  - **Não se realimenta.** O alerta de falha de e-mail é enviado por e-mail; a mensagem vai
    marcada como `alert=True` e uma falha dela **não** realimenta o contador (senão uma queda
    do SMTP viraria laço infinito).
  - **Nunca propaga.** Alertar é best-effort: nenhuma requisição pode falhar porque o aviso
    não saiu.

Escopo (honesto): contadores **em memória**, por processo — como o `InMemoryRateLimiter`. Com
uma instância (o caso do `fly.toml`) isso é exato; com réplicas, cada uma alerta pela sua
fatia. Um backend Redis encaixa aqui depois, atrás da mesma função `record()`.
"""
from __future__ import annotations
import logging
import os
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger("sereno.alerts")


@dataclass(frozen=True)
class Rule:
    """Uma regra de detecção: quantos sintomas, em quanto tempo, e o que dizer ao humano."""
    name: str
    threshold: int          # ocorrências para disparar
    window_s: int           # janela de contagem
    cooldown_s: int         # silêncio após disparar (anti-tempestade)
    subject: str            # assunto do e-mail (sem PII)
    hint: str               # o que fazer — um alerta sem próxima ação é ruído


# Limiares pensados para o PILOTO (N≈40, tráfego baixo): preferem avisar cedo a passar batido.
# Todos ajustáveis por ambiente — ver `_rule()`.
RULES: dict[str, Rule] = {
    "email_failure": Rule(
        "email_failure", threshold=3, window_s=900, cooldown_s=3600,
        subject="[Sereno] Falha na entrega de e-mail",
        hint=("O OTP de login e o aviso de evento adverso saem por e-mail. Verifique as "
              "credenciais SMTP e a fila. Enquanto isso, participantes podem não conseguir "
              "entrar e um evento adverso pode passar despercebido (RIPD R-06)."),
    ),
    "auth_failure": Rule(
        "auth_failure", threshold=25, window_s=300, cooldown_s=1800,
        subject="[Sereno] Rajada de falhas de autenticação",
        hint=("Muitas respostas 401 em pouco tempo — força bruta de OTP/senha ou token "
              "expirado em massa. Confira o rate limit e a trilha de auditoria."),
    ),
    "server_error": Rule(
        "server_error", threshold=10, window_s=300, cooldown_s=1800,
        subject="[Sereno] Erros de servidor em série",
        hint=("Várias respostas 5xx em pouco tempo. Verifique banco, Redis e o /ready antes "
              "que a coleta do dia seja perdida."),
    ),
    "research_access": Rule(
        "research_access", threshold=200, window_s=3600, cooldown_s=7200,
        subject="[Sereno] Volume atípico de acesso a dados de pesquisa",
        hint=("Muitos acessos às rotas de pesquisa/exportação numa hora. Pode ser trabalho "
              "legítimo de análise — confira **quem** na trilha de auditoria (RIPD R-03). "
              "Este aviso não identifica ninguém de propósito."),
    ),
}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _rule(name: str) -> Rule:
    """Regra com limiares do ambiente: ``ALERT_<REGRA>_{THRESHOLD,WINDOW_S,COOLDOWN_S}``."""
    base = RULES[name]
    up = name.upper()
    return Rule(
        base.name,
        threshold=_int_env(f"ALERT_{up}_THRESHOLD", base.threshold),
        window_s=_int_env(f"ALERT_{up}_WINDOW_S", base.window_s),
        cooldown_s=_int_env(f"ALERT_{up}_COOLDOWN_S", base.cooldown_s),
        subject=base.subject,
        hint=base.hint,
    )


_lock = threading.Lock()
_windows: dict[str, tuple[float, int]] = {}    # regra -> (início da janela, contagem)
_silent_until: dict[str, float] = {}           # regra -> instante em que pode alertar de novo


def enabled() -> bool:
    """Desligável por ambiente (`ALERTS_ENABLED=0`) — ligado por padrão."""
    from app.core.config import env_truthy
    return env_truthy(os.getenv("ALERTS_ENABLED", "1"))


def reset() -> None:
    """Zera janelas e cooldowns (testes; nunca chamado em produção)."""
    with _lock:
        _windows.clear()
        _silent_until.clear()


def record(rule_name: str, *, count: int = 1) -> None:
    """Registra ``count`` ocorrências do sintoma; dispara o alerta se cruzar o limiar.

    Best-effort e barato: pega o lock, mexe em dois dicionários e sai. Nunca propaga — é
    chamado de middleware e de caminho de entrega de e-mail, onde uma exceção seria pior
    que o alerta perdido."""
    try:
        if not enabled() or rule_name not in RULES:
            return
        rule = _rule(rule_name)
        now = time.monotonic()
        with _lock:
            start, current = _windows.get(rule_name, (now, 0))
            if now - start >= rule.window_s:
                start, current = now, 0        # janela fixa: virou, recomeça
            current += count
            _windows[rule_name] = (start, current)
            if current < rule.threshold or now < _silent_until.get(rule_name, 0.0):
                return
            # Vai disparar: silencia a regra e ZERA a janela ainda sob o lock, para duas
            # threads não dispararem o mesmo alerta em paralelo.
            _silent_until[rule_name] = now + rule.cooldown_s
            _windows[rule_name] = (now, 0)
        _fire(rule, current)
    except Exception:  # noqa: BLE001 — alerta jamais derruba quem o chamou
        logger.warning("Falha ao processar alerta '%s'.", rule_name)


def _fire(rule: Rule, count: int) -> None:
    """Emite o alerta: métrica + log estruturado + e-mail à equipe (se configurado)."""
    from app.core import metrics
    metrics.observe_alert(rule.name)
    logger.warning("alerta disparado", extra={"extra_fields": {
        "rule": rule.name, "count": count, "window_s": rule.window_s}})

    to = os.getenv("TEAM_NOTIFY_EMAIL")
    if not to:
        return                                  # sem destino, o log é o canal
    from app.core.email import EmailMessage, get_email_delivery
    body = (f"Regra: {rule.name}\n"
            f"Ocorrências: {count} em até {rule.window_s}s\n"
            f"Silenciada por: {rule.cooldown_s}s\n\n"
            f"{rule.hint}\n\n"
            "Este aviso é automático e não contém dados de participante.")
    # `alert=True`: uma falha ao entregar ESTE e-mail não realimenta o contador de falha de
    # e-mail — do contrário, SMTP fora geraria alerta que falha que gera alerta…
    get_email_delivery().deliver(EmailMessage(to=to, subject=rule.subject, body=body,
                                              alert=True))


def observe_response(*, path_template: str, status: int) -> None:
    """Traduz uma resposta HTTP nos sintomas que interessam. Chamado pelo middleware.

    Só rótulos de baixa cardinalidade (template de rota e status) — os mesmos que a métrica
    já usa; nada de caminho concreto, corpo ou identidade."""
    if status >= 500:
        record("server_error")
    elif status == 401:
        record("auth_failure")
    elif status < 400 and path_template.startswith(("/research", "/audit")):
        # R-03 (insider): volume de leitura do dado de pesquisa. Só o VOLUME — quem foi está
        # na auditoria, que é o lugar próprio para isso.
        record("research_access")
