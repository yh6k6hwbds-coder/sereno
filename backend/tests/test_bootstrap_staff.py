"""
tests/test_bootstrap_staff.py — O galo e o ovo do primeiro deploy (H3, ADR-112).

`POST /v1/staff` exige `user:manage`, que só um staff já existente tem; a tabela nasce vazia
e o `seed_demo.py` não cria staff. Banco novo = ninguém entra, e isso não estava em lista
nenhuma até a Fase H.

O que se prova aqui:

  1. Com a tabela vazia, o script cria as contas — e o convite é emitido para cada uma.
  2. **Nenhuma senha é definida.** A conta nasce com hash desconhecido: quem opera o deploy
     não ganha caminho para entrar como a pessoa que acabou de cadastrar (ADR-094).
  3. Com staff já existente, o script se **recusa** — dali em diante o caminho é a API, que
     registra quem convidou quem. `--force` é a saída para a instalação travada.
  4. A trilha de auditoria mostra que a conta nasceu FORA do fluxo normal, e sem PII.
  5. `--check` responde as duas perguntas do primeiro deploy: existe alguém? há DOIS admins
     (que é o que o descegamento exige — ADR-075)?
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest
from sqlalchemy import select

from app.core import auth
from app.core.models import StaffUser, StaffSetupToken, AuditLog


def _script():
    """Importa o script por caminho — `scripts/` não é pacote instalável."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(raiz, "scripts", "bootstrap_staff.py")
    spec = importlib.util.spec_from_file_location("bootstrap_staff", caminho)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def script(api, monkeypatch):
    """O script fala com o banco por `Session(get_engine())`; aqui, o engine é o do teste."""
    _client, TestSession = api
    engine = TestSession.kw["bind"]
    mod = _script()
    monkeypatch.setattr(mod, "get_engine", lambda: engine)
    return mod, TestSession


def test_cria_as_primeiras_contas_com_convite(script, capsys):
    mod, TestSession = script
    codigo = mod.main(["ana@uninta.edu.br", "bruno@uninta.edu.br"], "admin",
                      check_only=False, force=False, print_link=False)
    assert codigo == 0

    with TestSession() as s:
        contas = s.scalars(select(StaffUser).order_by(StaffUser.email)).all()
        assert [c.email for c in contas] == ["ana@uninta.edu.br", "bruno@uninta.edu.br"]
        assert all(c.role == "admin" and not c.mfa_enabled for c in contas)
        # Um convite pendente por conta, e nenhum token em claro no banco.
        tokens = s.scalars(select(StaffSetupToken)).all()
        assert len(tokens) == 2
        assert all(t.purpose == "invite" and not t.consumed for t in tokens)
        assert all(len(t.token_hash) == 64 for t in tokens)


def test_nenhuma_senha_e_definida(script):
    """A conta nasce com hash de senha aleatória DESCONHECIDA: nem quem roda o script entra."""
    mod, TestSession = script
    mod.main(["ana@uninta.edu.br"], "admin", check_only=False, force=False, print_link=False)
    with TestSession() as s:
        conta = s.scalar(select(StaffUser))
    # Nenhum palpite óbvio abre a conta — e não há como o script ter "escolhido" uma senha.
    for tentativa in ("", "admin", "sereno", "Senha-Forte-123", conta.email):
        assert not auth.verify_password(conta.password_hash, tentativa)


def test_recusa_quando_ja_ha_staff_e_force_libera(script, capsys):
    """Havendo alguém dentro, o caminho certo é a API — que registra quem convidou quem."""
    mod, TestSession = script
    mod.main(["ana@uninta.edu.br"], "admin", False, False, False)

    assert mod.main(["mario@uninta.edu.br"], "admin", False, False, False) == 1
    assert "RECUSADO" in capsys.readouterr().out
    with TestSession() as s:
        assert s.scalar(select(StaffUser).where(StaffUser.email == "mario@uninta.edu.br")) is None

    # --force é a saída da instalação travada (um admin só, e ninguém consegue entrar).
    assert mod.main(["mario@uninta.edu.br"], "admin", False, True, False) == 0
    with TestSession() as s:
        assert s.scalar(select(StaffUser).where(
            StaffUser.email == "mario@uninta.edu.br")) is not None


def test_email_repetido_nao_duplica_conta(script):
    mod, TestSession = script
    mod.main(["ana@uninta.edu.br"], "admin", False, False, False)
    mod.main(["ana@uninta.edu.br"], "admin", False, True, False)
    with TestSession() as s:
        assert len(s.scalars(select(StaffUser)).all()) == 1


@pytest.mark.parametrize("ruim", ["sem-arroba", "a b@x.com", "", "ana@uninta"])
def test_email_invalido_e_recusado_antes_de_criar(script, ruim):
    """O erro que interessa pegar é o de digitação que criaria uma conta INALCANÇÁVEL."""
    mod, TestSession = script
    assert mod.main([ruim], "admin", False, False, False) == 2
    with TestSession() as s:
        assert s.scalars(select(StaffUser)).all() == []


def test_trilha_mostra_que_a_conta_nasceu_fora_do_fluxo_normal(script):
    """Ator `system`, ação própria: quem audita vê que não houve admin convidando."""
    mod, TestSession = script
    mod.main(["ana@uninta.edu.br"], "admin", False, False, False)
    with TestSession() as s:
        linha = s.scalar(select(AuditLog).where(AuditLog.action == "staff.bootstrapped"))
        assert linha is not None
        assert linha.actor_type == "system" and linha.actor_id is None
        assert linha.meta["role"] == "admin"
        assert "ana@uninta.edu.br" not in str(linha.meta)     # sem PII na trilha


def test_check_cobra_o_segundo_admin(script, capsys):
    """Uma instalação com um admin só descobre isso na hora de descegar — tarde demais."""
    mod, TestSession = script
    assert mod.main([], "admin", check_only=True, force=False, print_link=False) == 1
    assert "nenhuma conta de staff" in capsys.readouterr().out

    mod.main(["ana@uninta.edu.br"], "admin", False, False, False)
    assert mod.main([], "admin", True, False, False) == 1        # um admin ainda não basta
    assert "DOIS admins" in capsys.readouterr().out

    mod.main(["bruno@uninta.edu.br"], "admin", False, True, False)
    assert mod.main([], "admin", True, False, False) == 0
    assert "admins ativos: 2" in capsys.readouterr().out


def test_print_link_so_imprime_quando_pedido(script, capsys, monkeypatch):
    """O link é segredo: sai no terminal só com a flag, e é o caminho antes de haver SMTP."""
    mod, _TestSession = script
    monkeypatch.setenv("STAFF_SETUP_URL", "https://app.exemplo/setup")

    mod.main(["ana@uninta.edu.br"], "admin", False, False, print_link=False)
    assert "token=" not in capsys.readouterr().out

    mod.main(["bruno@uninta.edu.br"], "admin", False, True, print_link=True)
    saida = capsys.readouterr().out
    assert "https://app.exemplo/setup?token=" in saida
    assert "segredo" in saida
