"""
tests/test_sweep_script.py — A varredura da 2ª semana, agendável sem credencial (F3.11).

O endpoint `POST /v1/discontinuations/evaluate` exige token de staff, e o login de staff exige
**MFA**. Agendar a chamada obrigaria a guardar credencial e segredo de segundo fator no
agendador — esvaziando o MFA para ganhar uma tarefa de rotina. O script roda dentro do
servidor, com o acesso ao banco que a aplicação já tem.

O que se prova aqui:

  1. O script descontinua quem a regra manda descontinuar — e é a MESMA regra do endpoint.
  2. `--dry-run` conta e **não grava**.
  3. Rodar de novo não descontinua ninguém duas vezes.
  4. A saída **não nomeia participante**: log de agendador é lido por quem opera
     infraestrutura, não necessariamente por quem tem acesso ao dado do estudo.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys

import pytest
from sqlalchemy import select

from app.core.models import Participant, Allocation, ProtocolDiscontinuation


def _script():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(raiz, "scripts", "sweep_discontinuations.py")
    spec = importlib.util.spec_from_file_location("sweep_discontinuations", caminho)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def script(api, monkeypatch):
    _client, TestSession = api
    mod = _script()
    monkeypatch.setattr(mod, "get_engine", lambda: TestSession.kw["bind"])
    monkeypatch.setattr(sys, "argv", ["sweep_discontinuations.py"])
    return mod, TestSession


def _sumido(TestSession, codigo: str, dias: int = 20):
    """Participante alocado há `dias`, sem sessão nenhuma — o caso que a regra existe para pegar."""
    alocado_em = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)
    with TestSession() as s:
        p = Participant(study_code=codigo); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded="A", block=1,
                         sequence_seed_ref="ref", allocated_at=alocado_em))
        s.commit()
        return p.id


def test_a_varredura_alcanca_quem_parou_de_abrir_o_app(script, capsys):
    mod, TestSession = script
    pid = _sumido(TestSession, "P-SW1")

    assert mod.main() == 0
    saida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert saida["discontinued"] == 1 and saida["dry_run"] is False

    with TestSession() as s:
        registro = s.scalar(select(ProtocolDiscontinuation).where(
            ProtocolDiscontinuation.participant_id == pid))
        assert registro is not None
        # Descontinuar NÃO exclui da análise: o ITT é o que separa isto de uma retirada.
        assert bool(registro.kept_in_itt) is True


def test_dry_run_conta_e_nao_grava(script, capsys, monkeypatch):
    mod, TestSession = script
    _sumido(TestSession, "P-SW2")
    monkeypatch.setattr(sys, "argv", ["sweep_discontinuations.py", "--dry-run"])

    assert mod.main() == 0
    saida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert saida["discontinued"] == 1 and saida["dry_run"] is True

    with TestSession() as s:
        assert s.scalars(select(ProtocolDiscontinuation)).all() == []


def test_rodar_de_novo_nao_descontinua_duas_vezes(script, capsys):
    """Agendador repete: a segunda passada tem de ser inócua."""
    mod, TestSession = script
    _sumido(TestSession, "P-SW3")

    mod.main()
    capsys.readouterr()
    assert mod.main() == 0
    saida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert saida["discontinued"] == 0

    with TestSession() as s:
        assert len(s.scalars(select(ProtocolDiscontinuation)).all()) == 1


def test_a_saida_nao_nomeia_participante(script, capsys):
    """Log de agendador é lido por quem opera infraestrutura, não por quem tem acesso ao dado."""
    mod, TestSession = script
    _sumido(TestSession, "P-SW4")

    mod.main()
    saida = capsys.readouterr().out
    assert "P-SW4" not in saida
    for proibido in ("study_code", "participant_id", "arm", "sham"):
        assert proibido not in saida
