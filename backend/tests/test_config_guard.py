"""
tests/test_config_guard.py — Guard de config de produção + selagem da chave A/B→condição.

Prova o endurecimento pré-piloto (ADR-077):
  - em produção, subir com a chave selada no default público OU com EMAIL_DEV_CONSOLE
    ligado é RECUSADO (fail-fast) — protege inegociáveis #2 (cegamento) e #6 (OTP em log);
  - fora de produção, os defaults de conveniência valem (nada levanta);
  - defesa em profundidade: `condition_for_arm` recusa o default público em produção;
  - o construtor de SMTP escolhe STARTTLS (587) vs SSL implícito (465) corretamente.
"""
from __future__ import annotations
import pytest

from app.core.config import validate_runtime_config, is_production, InsecureConfigError
from app.modules.sessions.service import condition_for_arm
from app.core.email import _build_from_env, SmtpEmailSender


def _prod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")


# --- guard de startup -------------------------------------------------------

def test_dev_is_noop_even_with_insecure_config(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)          # dev (default)
    monkeypatch.delenv("ARM_CONDITION_MAP", raising=False)
    monkeypatch.setenv("EMAIL_DEV_CONSOLE", "1")
    assert not is_production()
    validate_runtime_config()                              # não levanta em dev


def test_prod_without_sealed_map_refuses(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.delenv("ARM_CONDITION_MAP", raising=False)
    monkeypatch.delenv("EMAIL_DEV_CONSOLE", raising=False)
    with pytest.raises(InsecureConfigError, match="ARM_CONDITION_MAP"):
        validate_runtime_config()


def test_prod_with_email_console_refuses(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.setenv("ARM_CONDITION_MAP", "A:sham,B:active")   # selada OK
    monkeypatch.setenv("EMAIL_DEV_CONSOLE", "1")
    with pytest.raises(InsecureConfigError, match="EMAIL_DEV_CONSOLE"):
        validate_runtime_config()


def test_prod_well_configured_passes(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.setenv("ARM_CONDITION_MAP", "A:sham,B:active")
    monkeypatch.delenv("EMAIL_DEV_CONSOLE", raising=False)
    validate_runtime_config()                              # não levanta


# --- defesa em profundidade na resolução da condição ------------------------

def test_condition_uses_dev_default_off_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ARM_CONDITION_MAP", raising=False)
    assert condition_for_arm("A") == "active"              # default só-dev
    assert condition_for_arm("B") == "sham"


def test_condition_refuses_dev_default_in_production(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.delenv("ARM_CONDITION_MAP", raising=False)
    with pytest.raises(InsecureConfigError):
        condition_for_arm("A")


def test_condition_honors_custodian_map_in_production(monkeypatch):
    _prod(monkeypatch)
    monkeypatch.setenv("ARM_CONDITION_MAP", "A:sham,B:active")   # sorteio custodiado
    assert condition_for_arm("A") == "sham"
    assert condition_for_arm("B") == "active"


# --- seleção de transporte SMTP (STARTTLS vs SSL implícito) -----------------

def _smtp_env(monkeypatch, **over):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    for k in ("SMTP_PORT", "SMTP_USE_SSL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in over.items():
        monkeypatch.setenv(k, v)


def test_smtp_587_uses_starttls(monkeypatch):
    _smtp_env(monkeypatch, SMTP_PORT="587")
    s = _build_from_env()
    assert isinstance(s, SmtpEmailSender)
    assert s._use_ssl is False and s._use_tls is True


def test_smtp_465_autodetects_implicit_ssl(monkeypatch):
    _smtp_env(monkeypatch, SMTP_PORT="465")
    s = _build_from_env()
    assert isinstance(s, SmtpEmailSender)
    assert s._use_ssl is True and s._use_tls is False


def test_smtp_use_ssl_flag_forces_ssl_on_other_port(monkeypatch):
    _smtp_env(monkeypatch, SMTP_PORT="2525", SMTP_USE_SSL="1")
    s = _build_from_env()
    assert isinstance(s, SmtpEmailSender)
    assert s._use_ssl is True and s._use_tls is False
