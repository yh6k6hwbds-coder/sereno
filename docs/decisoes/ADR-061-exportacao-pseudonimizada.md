# ADR-061 — Exportação pseudonimizada (assíncrona) para análise

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend), 7 (análise/CONSORT)
- **Contexto de origem:** Fatia C6 do ROADMAP · **Depende de:** C1 (auditoria)
- **Relaciona-se com:** ADR-027 (braço codificado + chave selada), ADR-026 (PII), ADR-031 (fila assíncrona)

## Contexto
A análise (C7) precisa de um pacote de dados **pseudonimizado**, sem PII e **cego**. Faltava
gerar esse export. A tensão está no cegamento: a análise duplo-cega é feita **por grupo
codificado A/B**, mas o mapa A/B→ativo/sham fica **selado** até o *data lock*.

## Decisão
1. **`POST /v1/research/export`** (`export:request`): monta o CSV **reusando**
   `instruments_scoring.build_export_csv`; executa via um **job** e devolve `202 {job_id}`.
   **`GET /v1/research/export/{id}`** devolve o status (JSON) ou o **arquivo** (CSV) quando pronto.
2. **Conteúdo (decisão do mantenedor):** inclui o **braço CODIFICADO A/B** (`Grupo A`/`Grupo B`),
   necessário à análise cega, além de `study_code` (pseudônimo), escores basal/seguimento
   (GAD-7/PSQI/SUS), adesão, contagem de eventos adversos e o palpite de cegamento. **Nunca**
   PII, a **condição** (ativo/sham) nem a chave selada.
3. **Casos completos:** exporta participantes **alocados com baseline E seguimento** (a análise
   de desfechos usa o par basal→seguimento). Incompletos ficam de fora (perdas são tratadas no
   plano de análise, C7).
4. **Auditado:** o pedido grava `export.requested` (com `job_id`, sem PII/condição).
5. **Job como porta:** in-memory no piloto (roda inline, N pequeno; sem migração, sem Redis no
   CI); em produção troca-se por **RQ/Redis + armazenamento** (URLs assinadas).

## Alternativas consideradas
- **Incluir a condição (ativo/sham) no export.** Rejeitada: quebraria o cegamento; a condição só
  entra após o desbloqueio controlado (C5).
- **Omitir até o braço codificado A/B.** Rejeitada (decisão do mantenedor): a análise cega — em
  especial o **índice de Bang** e comparações exploratórias — precisa do grupo A/B; a proteção
  vem de manter **selada** a chave A/B→condição, não de esconder o código.
- **Persistir jobs no banco (tabela `ExportJob`).** Adiada: a porta in-memory evita migração;
  produção usa RQ + storage. (Trade-off: sem durabilidade — ver Consequências.)
- **Resposta síncrona 200 com o CSV.** Rejeitada: o contrato/roadmap pedem semântica assíncrona
  (202 + polling), preservável mesmo com execução inline no piloto.

## Consequências
- **Positivas:** C7 tem o insumo pseudonimizado e cego; nenhuma PII/condição vaza; pedido
  auditado; reaproveita a lógica de escores/CSV já validada. Suíte: 121 → 126 testes.
- **Custo/tradeoff (visão do analista):**
  - **Braço A/B no export:** quem tem `export:request` vê os grupos A/B — **intencional** para a
    análise cega; a separação real (A/B→condição) depende da chave selada (C5) permanecer fora.
  - **Job in-memory:** não é durável nem compartilhado entre processos; após reinício o `job_id`
    some. Produção **exige** RQ/Redis + storage. Documentado.
  - **Casos completos** excluem perdas/desistências deste export; a análise (C7) trata
    missingness explicitamente (não silenciar as perdas no relatório).
- **Pendências:** RQ + armazenamento (URLs assinadas) em prod; incluir métricas de perdas para o
  CONSORT; export incremental/particionado se o volume crescer (fora do piloto).

## Conformidade
CI verde exige `tests/test_export.py`: o CSV tem o braço **codificado** (Grupo A/B) e **não**
contém PII (e-mail) nem a condição (ativo/sham); casos incompletos ficam de fora; o pedido é
**auditado** (`export.requested`, sem PII/condição); fluxo de job (202 `{job_id}` → GET CSV;
job inexistente → 404); negações 401 (sem token) e 403 (sem `export:request`).
