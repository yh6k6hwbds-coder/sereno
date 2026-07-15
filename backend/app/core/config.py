"""
core/config.py — Ambiente (dev/produção) e validação de runtime (fail-fast em produção).

Centraliza a distinção dev/produção (``APP_ENV``) e as invariantes que **não podem valer
em produção**, porque violam decisões inegociáveis do ``CLAUDE.md``:

  - a **chave selada** A/B→condição (``ARM_CONDITION_MAP``) precisa ser custodiada por fora
    e **jamais** cair no default público — do contrário o braço codificado (exportado como
    A/B) revela ativo/sham e o cegamento cai (inegociável #2);
  - ``EMAIL_DEV_CONSOLE`` imprime o código OTP no log — proibido em produção (inegociável #6).

``validate_runtime_config()`` é chamada no startup (``create_app``) e **levanta** em produção
se algo acima estiver errado; em dev/teste é no-op (defaults de conveniência valem). A
recusa é reforçada em profundidade no ponto de uso (``sessions.service._sealed_map``).
"""
from __future__ import annotations
import os

# Default do mapa selado aceitável SÓ em dev/teste. Em produção é recusado (o mapa real é
# um sorteio custodiado, setado como secret e nunca versionado). Ver ADR-077.
DEV_ARM_CONDITION_MAP = "A:active,B:sham"


class InsecureConfigError(RuntimeError):
    """Config que violaria uma decisão inegociável em produção (fail-fast no startup)."""


def app_env() -> str:
    return os.getenv("APP_ENV", "dev").strip().lower()


def is_production() -> bool:
    return app_env() in ("production", "prod")


def env_truthy(v: str | None) -> bool:
    # Mesma semântica de "ligado" usada pelo email.py: qualquer valor não-vazio conta,
    # exceto os desligamentos explícitos comuns.
    return bool(v) and v.strip().lower() not in ("0", "false", "no", "off")


def security_fail_open() -> bool:
    """Postura quando o backend de rate limit/denylist (Redis) está indisponível.

    ``True`` (padrão) = **fail-open**: prioriza disponibilidade — uma queda do Redis NÃO
    derruba login/OTP nem toda rota autenticada. O rate limit deixa passar e a denylist
    trata o token como não-revogado (a defesa fica best-effort durante a falha; tokens de
    acesso têm TTL curto). ``False`` = **fail-closed**: prioriza a defesa (429/401) ao custo
    de disponibilidade. Configurável por ``SECURITY_FAIL_OPEN``. Ver ADR-079."""
    return env_truthy(os.getenv("SECURITY_FAIL_OPEN", "1"))


def validate_runtime_config() -> None:
    """Falha rápido se a config de produção violar uma decisão inegociável.

    No-op fora de produção (``APP_ENV`` != production/prod), onde os defaults de
    conveniência são intencionais."""
    if not is_production():
        return
    problems: list[str] = []
    if not os.getenv("ARM_CONDITION_MAP"):
        problems.append(
            "ARM_CONDITION_MAP ausente: a chave selada A/B→condição não pode cair no default "
            "público (quebraria o cegamento — inegociável #2). Configure-a como secret "
            "custodiado, fora do repositório (ver ADR-077).")
    if env_truthy(os.getenv("EMAIL_DEV_CONSOLE")):
        problems.append(
            "EMAIL_DEV_CONSOLE ligado em produção: imprimiria o código OTP no log "
            "(inegociável #6). Remova e configure SMTP real.")
    if problems:
        raise InsecureConfigError(" | ".join(problems))
