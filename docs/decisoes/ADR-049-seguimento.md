# ADR-049 — Seguimento (PSQI+GAD-7+SUS+cegamento) e bruto reprodutível

- **Status:** Aceito
- **Data:** 2026-07-03
- **Etapas relacionadas:** 4 (instrumentos), 7 (análise)
- **Contexto de origem:** 9ª fatia (fecha a espinha científica)

## Decisão
1. **Reuso do motor de escore validado** (PSQI, GAD-7) + **SUS** (usabilidade) + **item de
   integridade do cegamento** (`blinding_guess`) num único `POST /v1/participants/me/followup`.
2. **Bruto + escore versionado** (como a linha de base): estendida a tabela `followup_assessment`
   com `gad7_items`, `psqi_input`, `sus_items` (JSON) via **migração incremental**; `sus_score`
   corrigido de `SMALLINT` para `Numeric(5,1)` (o SUS pode ser X,5).
3. **`blinding_guess` é só o palpite** — NUNCA comparado nem substituído pelo braço real no
   backend. Alimenta o índice de Bang (Etapa 7) mantendo o cegamento intacto.
4. **Um seguimento por participante** (409).

## Consequências
- **Positivas:** espinha científica completa (linha de base → intervenção → seguimento → análise);
  reprodutibilidade (recomputável do bruto); cegamento preservado (testado: palpite ≠ verdade).
- **Tradeoff:** três migrações agora; a alteração de tipo de coluna foi feita antes de haver dados.

## Conformidade
CI exige a suíte de seguimento passando (escores corretos, bruto persistido, palpite gravado como
palpite, duplicidade, validação).
