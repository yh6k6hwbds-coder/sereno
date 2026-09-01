# ADR-115 — O contrato passa a ser verificado no CI, e a superfície pública encolhe

- **Status:** Aceito
- **Data:** 2026-09-01
- **Decisores:** Arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend), 1 (arquitetura/contrato)
- **Contexto de origem:** varredura final antes da conclusão do piloto.
- **Relaciona-se com:** ADR-111 (o `GET /sessions` prometido e ausente), ADR-113 (o stub que
  respondia 200), Definição de Pronto do `ROADMAP.md` (item 1).

## Contexto

O `shared-contracts/openapi.yaml` é a **fonte de verdade da API** (`CLAUDE.md`), e a Definição de
Pronto manda atualizá-lo **antes** do código. **Nada verificava isso.** O CI validava que o
contrato é um OpenAPI *bem formado* — não que ele descreva o app que existe.

A falta cobrou caro duas vezes na Fase H, e nas duas direções:

- **`GET /sessions` estava documentado e não existia.** Um cliente escrito a partir do contrato
  tomava 405. Só apareceu ao inventariar o que a equipe consegue ler (ADR-111) — por acaso, não
  por verificação.
- **Sete rotas `_status` estavam no ar, públicas e não documentadas.** Resto do andaime de
  scaffolding: `/v1/allocation/_status`, `/v1/audit/_status`, `/v1/consent/_status`,
  `/v1/followup/_status`, `/v1/baseline/_status`, `/v1/research/_status`, `/v1/sessions/_status`.
  Duas respondiam, literalmente, `{"status": "stub"}`; a do consentimento devolvia a versão do
  TCLE **sem autenticação**.

Uma auditoria manual mostrou o placar: **55 operações no contrato, 62 no app**.

## Decisão

**1. As sete rotas `_status` saíram.** Não estavam no contrato, nenhum teste as cobria, o
aplicativo não as chamava, e nenhuma delas exigia autenticação. Não é limpeza cosmética: o piloto
ainda vai passar por **pentest externo** (F3.5), e superfície não documentada é superfície que
ninguém revisou. `/health`, `/ready` e `/metrics` continuam — esses têm dono, propósito e, no caso
do `/metrics`, guarda opcional por token.

**2. Um teste passa a comparar contrato e implementação, nas duas direções** —
`tests/test_contrato_x_implementacao.py`, no job de backend que já existe. As duas direções são
defeito, por motivos diferentes:

- **prometido e ausente** engana quem integra pelo contrato, que é como o app é escrito;
- **exposto e não documentado** é a superfície que ninguém revisou.

Três detalhes que fazem o teste valer:

- **Compara caminho a caminho, não contagem.** Uma contagem igual com duas trocas se cancela e
  passaria; a mensagem de falha nomeia a rota exata que divergiu.
- **Normaliza o nome do parâmetro** (`{session_id}` ≡ `{id}`): o nome é escolha de quem escreve o
  handler, não parte do endereço. Sem isso o teste acusaria toda rota parametrizada.
- **Usa `app.openapi()`, não `app.routes`.** Nesta versão do FastAPI os routers incluídos ficam
  como `_IncludedRouter` preguiçoso, e varrer `app.routes` devolve **zero** rotas sob `/v1` — um
  teste escrito assim passaria sempre, verificando nada. Há um terceiro caso que guarda contra
  isso: se qualquer dos dois conjuntos vier quase vazio, ele falha.

Depois da limpeza: **55 = 55**, exato nos dois sentidos.

## Consequências

- A regra 1 da Definição de Pronto deixa de depender de disciplina e passa a ser verificada.
- Quem acrescentar uma rota sem documentá-la (ou documentar sem implementar) **descobre no CI**,
  com o nome da rota na mensagem — não meses depois, ao inventariar outra coisa.
- A superfície pública da API caiu de 62 para 55 operações antes do pentest.
- O teste é barato (compara dois dicionários) e roda junto da suíte.

## Alternativas consideradas

**Gerar o contrato a partir do código (`app.openapi()` como fonte de verdade).** Rejeitada: o
contrato é escrito à mão de propósito — carrega descrições, exemplos e o *porquê* de cada rota,
que é o que o app Flutter e o revisor leem. Gerá-lo transformaria o contrato em espelho do código,
e a regra "contrato **antes** do código" perderia sentido: não existiria mais nada para divergir.

**Comparar também schemas e códigos de resposta.** Rejeitada por ora: o ganho cai rápido e o custo
de manutenção sobe (o FastAPI gera schemas com nomes e formas próprios). O que quebrava de verdade
era a existência da rota.

**Manter os `_status` documentando-os.** Rejeitada: seria documentar sete rotas que não fazem nada
— duas admitindo que são stub. O que elas ofereciam (o módulo está no ar) o `/ready` já oferece,
com significado.
