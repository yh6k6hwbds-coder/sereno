# ADR-084 — Ingestão de vestíveis: seam desacoplado (porta, sem device nem persistência)

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** Fase E (E2 — ingestão de vestíveis)
- **Contexto de origem:** ROADMAP E2 — "porta de entrada para FC/sono de wearables via adaptador
  desacoplado". Fatia **explicitamente fora do MVP** (CLAUDE.md); executada com sign-off do
  mantenedor, no **escopo mínimo** (porta + stub), não integração de device real.
- **Relaciona-se com:** inegociável #5 (recomendador por regras; ML/sinais externos não decidem
  ao vivo), inegociável #6 (PII/LGPD; dado de saúde é sensível), ADR-063 (`EmailSender` porta),
  ADR-082 (`AudioStorage` porta) — mesmo padrão de porta com adaptador Null/Memory.

## Contexto
A visão de longo prazo prevê ingerir FC/sono de vestíveis, mas o CLAUDE.md trava o escopo no
piloto e marca wearables como "registrar no roadmap e **perguntar**, não implementar". Com o
sign-off explícito do mantenedor para a E2, a decisão é entregar **só o seam** — o contrato de
ingestão e a porta desacoplada onde uma integração real (SDK de device, webhook de provedor ou
persistência cifrada) encaixa depois — **sem** trazer SDK, sem persistir dado de saúde e sem
qualquer caminho para os sinais influenciarem a decisão ao vivo.

## Decisão
1. **`POST /v1/wearables/readings`** (participante, novo RBAC `wearable:write`): recebe um lote de
   leituras **canônicas** (`kind` FC/sono, `taken_at`, `value`, `unit`, `source`), já normalizadas
   no device (HealthKit/Google Fit), e encaminha ao sink. Responde **202** (recebido) + contagem.
2. **Porta `WearableSink` desacoplada** (`modules/wearables/sink.py`), no mesmo padrão de
   `EmailSender`/`AudioStorage`: `Null` (**padrão**, aceita e **descarta**), `Memory` (teste/seam
   ponta a ponta), selecionável por `WEARABLE_SINK`. Persistência/provedor real são **adaptadores
   futuros** desta mesma porta.
3. **Não persiste no padrão** e **sem migração**: é preparação, não construção (CLAUDE.md:
   "escalabilidade preparada, não construída"). Quando a persistência entrar, o dado de saúde
   deverá ser tratado como **sensível** (cifra/separação, como a PII do C4 — inegociável #6).
4. **Beco sem saída quanto à decisão (inegociável #5):** nada em `wearables` importa ou alimenta o
   recomendador; o `feature_vector` da decisão **não** ganha campo de vestível. Um teste guarda
   isso (ingerir não cria recomendação; o vetor mantém o conjunto fixo de chaves).
5. **Sem valor de saúde em log (inegociável #6):** a auditoria (`wearable.ingested`) grava **só a
   contagem** — nunca o valor, horário ou unidade.

## Alternativas consideradas
- **Integrar um SDK/provedor real agora (pull).** Rejeitada: exige credenciais/residência e é
  "construir" — fora do MVP. A porta deixa o pull como adaptador futuro.
- **Persistir as leituras já (E2-médio).** Adiada por decisão de escopo (mínimo): traria tabela +
  migração + tratamento de dado sensível. Fica como a fatia seguinte, plugando um `DbSink`.
- **Deixar as leituras acessíveis ao recomendador "para enriquecer".** Rejeitada: violaria o
  inegociável #5 (sinal externo não valida decisão ao vivo) e o escopo. O seam é deliberadamente
  desconectado da decisão.
- **200 em vez de 202.** Rejeitada: **202** é honesto para um sink que, no padrão, não persiste —
  "recebido", sem prometer armazenamento durável.

## Consequências
- **Positivas:** contrato de ingestão + porta prontos e **testáveis sem device**; integração real
  (SDK/persistência) encaixa sem mexer no cliente nem no router. Cegamento e regras intactos.
  Suíte 241 → 249 (+8). Sem migração (fatia leve).
- **Custo/tradeoff:** no padrão as leituras são **descartadas** — o `202` sinaliza isso, mas o
  ganho real só vem com um adaptador de persistência/provedor. É a "preparação" pedida pela E2.
- **Pendências:** adaptador de persistência (tabela + migração + **cifra/separação** do dado de
  saúde), consulta de leituras para pesquisa (offline/cego, se e quando fizer sentido), e
  mapeadores por provedor (payload cru → leitura canônica) quando um device real for integrado.

## Conformidade
CI verde exige `tests/test_wearables.py`: participante ingere lote → 202 + contagem; NullSink
padrão não persiste; MemorySink recebe as leituras ponta a ponta; staff 403; anônimo 401; payload
inválido 422; auditoria **sem valores de saúde** (só contagem); **ingerir não toca o recomendador
ao vivo** (sem recomendação criada; `feature_vector` sem campo de vestível). Sem segredo
versionado; sem PII/valor de saúde em log; inegociáveis #5/#6 preservados.
