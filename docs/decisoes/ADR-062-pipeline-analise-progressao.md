# ADR-062 — Pipeline de análise + critérios de progressão (relatório cego)

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 7 (análise/CONSORT-pilot)
- **Contexto de origem:** Fatia C7 do ROADMAP · **Depende de:** C6 (exportação)
- **Relaciona-se com:** ADR-037/038/039/040 (enquadramento, Bang, progressão, exploratórios), ADR-061

## Contexto
Faltava consolidar o **plano de análise** num relatório reprodutível: viabilidade/adesão/
retenção, usabilidade, **índice de Bang** (cegamento), testes exploratórios e **critérios de
progressão** (semáforo CONSORT-pilot). O `analysis_plan.py` já tinha os núcleos estatísticos;
faltava agregá-los sobre os dados e expor o resultado — **sem** decidir eficácia ao vivo.

## Decisão
1. **`GET /v1/research/analysis`** (`research:read`) devolve um **relatório JSON reprodutível e
   CEGO** (por braço CODIFICADO A/B): funil de inscrição, viabilidade (adesão/retenção com IC95%
   de Wilson), usabilidade (SUS, descritivos), **índice de Bang por braço**, exploratórios
   (mudança intra-braço e entre braços em GAD-7/PSQI, com seleção de teste por normalidade) e o
   **semáforo de progressão**.
2. **`progression_semaphore`** (novo em `analysis_plan.py`): critérios **pré-especificados** e
   determinísticos (adesão, retenção, segurança, cegamento) → verde/amarelo/vermelho; o geral é o
   **pior** critério. Qualquer EA **grave** marca vermelho; cegamento não mantido marca amarelo.
3. **Dados via a exportação cega** (`gather_export_rows`): casos completos, braço codificado, sem
   PII nem condição. O índice de Bang vem do `blinding_guess` vs braço codificado.
4. **Robustez:** floats não-finitos (p-valor indefinido em dados degenerados — braço com escores
   idênticos) são convertidos para `null` (`_json_safe`), mantendo o relatório honesto e válido.
5. **Enquadramento inegociável:** piloto de VIABILIDADE; exploratórios são geradores de hipótese;
   **nada decide eficácia nem desfecho ao vivo** — o semáforo **recomenda**, humanos decidem.

## Alternativas consideradas
- **Consumir o arquivo CSV do C6.** Rejeitada: reprocessar CSV é frágil; agregamos direto do
  banco com a **mesma** função de coleta (`gather_export_rows`) — uma fonte de verdade.
- **Índice de James (em vez de Bang).** Deferida (como já registrado no `analysis_plan`): a
  normalização do James é sutil; usa-se **Bang** (validado) e recomenda-se James com pacote
  validado (R 'BI') na análise final.
- **Embutir os limiares de progressão como “verdade”.** Rejeitada: os valores definitivos vêm do
  **protocolo/CEP**; o serviço traz limiares **ilustrativos configuráveis** e a lógica determinística.
- **Auditar a leitura do relatório.** Não feito: é derivação read-only (sem mudança de estado); o
  que é auditado é o **pedido de exportação** (C6), que produz o dado.

## Consequências
- **Positivas:** fecha o ciclo científico (export → análise) com um relatório cego e reprodutível;
  reusa estatística validada; semáforo pré-especificado apoia a decisão de progressão. Suíte:
  126 → 132 testes.
- **Custo/tradeoff (visão do analista):**
  - **Casos completos** para desfechos: perdas não entram nos exploratórios; o relatório expõe os
    denominadores (alocados vs casos completos) para leitura honesta das perdas.
  - **Dados degenerados** → p-valor `null` (não um número enganoso); interpretar como indefinido.
  - **Limiares ilustrativos**: trocar pelos do protocolo antes do relatório final; o `note` deixa
    o enquadramento explícito.
- **Pendências:** índice de James validado; IC de Bang por método fechado (hoje bootstrap
  ilustrativo); correção de multiplicidade (não aplicada, por decisão — exploratórios α=5%).

## Conformidade
CI verde exige `tests/test_analysis.py`: o semáforo mapeia limiares corretamente (verde/amarelo/
vermelho/indeterminado); o relatório tem as seções esperadas e **não** contém condição (ativo/
sham) nem PII; o índice de Bang detecta desblindagem (palpites corretos → BI=1, cegamento
amarelo) e "não sei" → cegamento mantido; relatório vazio é seguro; RBAC (403 participante, 401
sem token).
