"""
tests/test_contrato_x_implementacao.py — O contrato e o código contam a mesma história.

`shared-contracts/openapi.yaml` é a **fonte de verdade da API** (CLAUDE.md), e a Definição de
Pronto manda atualizá-lo **antes** do código. Nada verificava isso — e a falta cobrou caro duas
vezes na Fase H:

  * `GET /sessions` estava **documentado e não existia**: um cliente escrito a partir do contrato
    tomava 405, e só se descobriu ao inventariar o que a equipe consegue ler (ADR-111);
  * sete rotas `_status`, resto do andaime de scaffolding, ficaram **públicas e não documentadas**
    até esta varredura — duas delas respondendo, literalmente, `{"status": "stub"}`.

As duas direções são defeito, e por motivos diferentes:

  * **prometido e ausente** engana quem integra pelo contrato, que é como o app é escrito;
  * **exposto e não documentado** é superfície que ninguém revisou — e o piloto ainda vai passar
    por pentest externo (F3.5).

Comparar caminho a caminho, e não só contar, é o que faz o teste dizer **qual** rota divergiu:
uma contagem igual com duas trocas se cancela e passa.
"""
from __future__ import annotations

import io
import os

import pytest
import yaml

from app.main import app

VERBOS = ("get", "post", "put", "patch", "delete")


def _normaliza(caminho: str) -> str:
    """O contrato chama o parâmetro de `{id}`; o código, de `{session_id}`, `{event_id}`…

    São a mesma rota: o nome do parâmetro é escolha de quem escreve o handler, não parte do
    endereço. Sem isto, o teste acusaria divergência em toda rota com parâmetro."""
    return "/".join("{id}" if p.startswith("{") and p.endswith("}") else p
                    for p in caminho.split("/"))


def _operacoes(paths: dict, prefixo: str = "") -> set[tuple[str, str]]:
    return {(verbo.upper(), _normaliza(prefixo + caminho))
            for caminho, item in paths.items()
            for verbo in item if verbo in VERBOS}


def _contrato() -> set[tuple[str, str]]:
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    caminho = os.path.join(raiz, "shared-contracts", "openapi.yaml")
    if not os.path.exists(caminho):
        pytest.skip("shared-contracts/openapi.yaml não disponível neste ambiente")
    with io.open(caminho, encoding="utf-8") as f:
        return _operacoes(yaml.safe_load(f)["paths"], "/v1")


def _implementadas() -> set[tuple[str, str]]:
    # `app.openapi()` descreve o que o app REALMENTE serve — inclusive routers incluídos de
    # forma preguiçosa, que não aparecem varrendo `app.routes`.
    return {(m, c) for m, c in _operacoes(app.openapi()["paths"]) if c.startswith("/v1")}


def test_o_contrato_nao_promete_rota_que_nao_existe():
    """Quem escreve um cliente a partir do contrato não pode tomar 404/405."""
    faltando = sorted(_contrato() - _implementadas())
    assert not faltando, (
        "o contrato promete rotas que o app não serve — implemente ou remova do contrato:\n"
        + "\n".join(f"  {m} {c}" for m, c in faltando))


def test_o_app_nao_expoe_rota_fora_do_contrato():
    """Superfície não documentada é superfície que ninguém revisou."""
    sobrando = sorted(_implementadas() - _contrato())
    assert not sobrando, (
        "o app expõe rotas ausentes do contrato — documente-as ou remova-as:\n"
        + "\n".join(f"  {m} {c}" for m, c in sobrando))


def test_a_comparacao_esta_de_fato_comparando():
    """Guarda do próprio teste: um erro de caminho ou de parsing deixaria os dois conjuntos
    vazios, e os dois testes acima passariam sem verificar nada."""
    assert len(_contrato()) > 40
    assert len(_implementadas()) > 40
