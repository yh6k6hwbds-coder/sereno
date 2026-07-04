# ADR-044 — Linha de base (PSQI + GAD-7): bruto + escore versionado

- **Status:** Aceito
- **Data:** 2026-07-03
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 4 (instrumentos/escores), 5 (backend)
- **Contexto de origem:** 3ª fatia vertical (primeiro dado científico no banco)

## Contexto
A linha de base é o primeiro dado clínico do estudo. Precisa ser pontuada de forma
determinística, reprodutível e auditável, e entrar já com autenticação real.

## Decisão
1. **Escore no servidor, reusando o módulo já validado** (`instruments_scoring.py`) —
   nada de reimplementar cálculo; o módulo é a única fonte de verdade do escore.
2. **Persistir BRUTO + escore VERSIONADO**: `gad7_items` e `psqi_input` (JSON) mais
   `gad7_total`, `psqi_global` e `score_version` (`gad7:1.0.0|psqi:1.0.0`). Guardar o
   bruto permite recalcular componentes se o algoritmo evoluir (reprodutibilidade).
3. **`hours_in_bed` é enviado pelo cliente** (derivado de deitar→levantar), pois o
   escorador validado recebe esse campo diretamente. Mantém o backend fino e o
   escorador intacto; o contrato documenta o campo.
4. **Regra de domínio no servidor**: `hours_slept > hours_in_bed` → 422 (a validação em
   tempo real que se recomendou na Etapa 4).
5. **Uma linha de base por participante** → 409 em duplicata.
6. **Endpoint alinhado ao contrato**: `POST /v1/participants/me/baseline`; o `openapi.yaml`
   foi atualizado ANTES de fechar a fatia (schema `PSQIIn` + `ScoreOut` enriquecido).

## Alternativas consideradas
- **Guardar só o escore final.** Rejeitada: impede recomputar e auditar; ruim para o CEP.
- **Aceitar horário de deitar/levantar e computar `hours_in_bed` no backend.** Adiada:
  introduziria lógica de tempo não coberta pelo módulo validado; o cliente deriva por ora.
  Se necessário, migrar esse cálculo para o servidor numa fatia futura (mais auditável).

## Consequências
- **Positivas:** dado científico reprodutível e versionado; escore consistente com a Etapa 4;
  validação de domínio evita lixo estatístico.
- **Custo/tradeoff:** parte do cálculo (horas na cama) fica no cliente; documentado e reversível.
- **Pendências:** congelar `score_version` no protocolo/CEP antes da coleta (já previsto no CLAUDE.md).

## Conformidade
CI verde exige a suíte de baseline passando (escore correto + persistência do bruto +
validação + duplicidade) e o OpenAPI válido.
