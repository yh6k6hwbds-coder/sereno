# ADR-048 — Telemetria de desfechos: pós-sessão e diário de sono

- **Status:** Aceito
- **Data:** 2026-07-03
- **Etapas relacionadas:** 1 (desfechos), 4 (métricas)
- **Contexto de origem:** 8ª fatia (captura de desfechos do participante)

## Decisão
1. **Questionário pós-sessão** (`POST /v1/sessions/{id}/survey`): 6 itens (0–4 + booleano),
   **ligado à sessão do próprio participante** (proteção contra IDOR → 404), **um por sessão**
   (unicidade → 409).
2. **Diário de sono** (`POST /v1/diary`): latência, despertares, duração, qualidade;
   **um registro por participante por dia** (unicidade → 409).
3. Ambos exigem participante autenticado + RBAC (`session:write` / `diary:write`); validação
   de faixa em problem+json (422).

## Alternativas consideradas
- **Permitir múltiplos registros por dia/sessão.** Rejeitada: duplicidade polui a análise; a
  unicidade é imposta no banco (constraints já existentes) e na API.
- **Diário como parte do PSQI.** Rejeitada: são construtos distintos (diário = granularidade
  diária, exploratório; PSQI = desfecho). Mantidos separados (ver postura da Etapa 4/7).

## Consequências
- **Positivas:** desfechos de adesão/experiência capturados com integridade (sem duplicata,
  sem IDOR), prontos para a exportação e a análise (Etapa 7).
- **Pendências:** seguimento (PSQI/GAD-7/SUS + item de cegamento) fecha o par com a linha de base.

## Conformidade
CI exige a suíte de desfechos passando (persistência, duplicidade, IDOR, validação, RBAC).
