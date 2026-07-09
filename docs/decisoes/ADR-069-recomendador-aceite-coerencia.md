# ADR-069 — Fecho do loop do recomendador (aceite + coerência)

- **Status:** Aceito
- **Data:** 2026-07-09
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 6 (recomendador), 7 (análise/exploratórios)
- **Contexto de origem:** Continuação de E1 (pendências do ADR-068), escopo liberado pelo mantenedor
- **Relaciona-se com:** ADR-068 (recomendador ao vivo), ADR-035 (registro + ML só offline),
  ADR-062 (relatórios de pesquisa cegos), ADR-040 (exploratórios como geradores de hipótese)

## Contexto
O ADR-068 entregou a recomendação ao vivo e o registro, mas deixou o **loop aberto**: não havia
como o participante indicar se **aceitou** a sugestão, e o `coherence_report` (já escrito no motor)
não estava ligado a nenhuma rota. Sem o aceite, o desfecho exploratório de **coerência** da Etapa 1
não podia ser calculado sobre dados reais.

## Decisão
1. **Captura de aceite** — `POST /v1/recommendations/{rec_id}/accept` (participante, `recommend:read`):
   grava `accepted` (true/false) na **própria** recomendação. Decisão **única** (409 se já registrada);
   recomendação de outro participante → **404** (anti-IDOR, não revela existência).
2. **Relatório de coerência** — `GET /v1/research/recommendation-coherence` (staff `research:read`):
   reúsa `coherence_report` sobre todo o `recommendation_log`, devolvendo **alinhamento
   objetivo→banda** (QA do ruleset) e **taxa de aceitação**. É **CEGO** — não há braço no
   `recommendation_log` — e vive no módulo de pesquisa, ao lado de `/research/analysis`.
3. **Honestidade sobre o que ainda não dá:** as **médias de relaxamento** (aceitas vs recusadas)
   dependem de um vínculo recomendação→sessão→pós-sessão ainda **não modelado**; saem como `null`
   em vez de inventar um número.

## Alternativas consideradas
- **Permitir mudar o aceite depois (update livre).** Rejeitada por ora: decisão única é mais simples
  e suficiente para o sinal exploratório; reabertura pode ser fatia futura se houver necessidade.
- **Fabricar/estimar a média de relaxamento sem o vínculo real.** Rejeitada: seria overclaim; melhor
  `null` explícito e a pendência registrada.
- **Colocar a coerência no router do recomendador (participante).** Rejeitada: é leitura de pesquisa
  (staff, cego) — pertence a `/research`, com `research:read`.

## Consequências
- **Positivas:** o loop do recomendador fecha ponta a ponta; o desfecho exploratório de coerência
  passa a ser calculável sobre dados reais, mantendo o enquadramento de **hipótese** (sem eficácia).
  Suíte backend: 177 → **185 testes**; cobertura **87,8%**; `router`/`service` do recomendador a 100%.
- **Custo/tradeoff (visão do analista):** métricas de relaxamento ficam `null` até o vínculo
  rec→sessão existir — é uma lacuna **explícita**, não um erro silencioso. A taxa de aceitação conta
  como "aceito" apenas `accepted = true` (recusa e indecisão contam como não-aceito), coerente com
  "taxa de aceitação explícita".
- **Pendências:** vínculo recomendação→sessão para habilitar as médias de relaxamento; janela
  temporal do EA (herdada do ADR-068); guardrail de tolerabilidade ao vivo a partir da última
  pós-sessão.

## Conformidade
CI verde exige `tests/test_recommender_loop.py`: aceite grava a decisão (true/false); segundo aceite
→ 409; aceitar recomendação alheia → 404 (IDOR); id inexistente → 404; 401 sem token. Coerência
(staff) devolve `n`, `goal_alignment_rate` e `acceptance_rate` corretos, `mean_relaxation_*` = null,
e **nenhum termo de braço** no relatório; participante recebe 403.
