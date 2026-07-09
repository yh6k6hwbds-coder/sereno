# ADR-068 — Recomendador por regras ao vivo (endpoint + registro)

- **Status:** Aceito
- **Data:** 2026-07-09
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 6 (recomendador), 5 (backend/segurança)
- **Contexto de origem:** Fatia E1 do ROADMAP (Fase E — pós-piloto; escopo liberado pelo mantenedor)
- **Relaciona-se com:** ADR-006/032 (regras, não ML) **[inegociável]**, ADR-033 (seleção restrita à
  biblioteca validada) **[inegociável]**, ADR-034 (guardrails antes das regras), ADR-035
  (registro + `feature_vector`; ML nunca decide ao vivo), ADR-036 (`ruleset_version`),
  ADR-015/046 (handle neutro, resolução do braço só no servidor), ADR-057 (triagem/elegibilidade)

## Contexto
O motor de regras (`recommender.py`) já existia, completo e testado como lógica pura, mas **sem
endpoint** (o router era um stub) e **sem persistência** — a tabela `recommendation_log` existia
vazia. A fatia E1 liga o motor a uma rota real do participante, mantendo todas as decisões
inegociáveis da Etapa 6.

## Decisão
1. **Endpoint** `POST /v1/recommendations` (participante, nova permissão `recommend:read`):
   recebe **contexto autorrelatado** (`goal`, `sleep_issue`, `time_of_day`) e devolve um **handle
   NEUTRO** da biblioteca validada, com regra/versão, `flag_review`, aviso e nota de evidência.
2. **Sinais de segurança resolvidos NO SERVIDOR** (`service.py`), nunca aceitos do cliente:
   - `recent_adverse_severity` ← evento adverso mais recente do participante (`adverse_event`);
   - `contraindicated` ← triagem mais recente **inelegível** (`screening.eligible = false`).
   Assim os guardrails (de-escalonar / não recomendar) não são burláveis por payload.
3. **Registro** em `recommendation_log` a cada chamada: `inputs` (snapshot + `feature_vector` para
   ML futuro), `rule_id`, `rule_version`, `suggested_protocol`. O caso `no_recommendation`
   (contraindicação) é registrado **fielmente com `suggested_protocol = NULL`** — daí a migração
   `b2c3d4e5f6a7` que torna a coluna nullable.
4. **Resposta enxuta e neutra:** o cliente recebe só o necessário; `input_snapshot`/`feature_vector`
   ficam apenas no log (auditoria/ML). Nada na resposta revela ativo/sham.

## Alternativas consideradas
- **Aceitar os sinais de segurança do cliente.** Rejeitada: seria burlável e violaria a postura de
  segurança; sinais sensíveis são autoritativos no servidor (como a resolução do braço).
- **Usar sentinela (ex.: `"none"`) em vez de NULL para `no_recommendation`.** Rejeitada: NULL
  representa a ausência de protocolo com fidelidade e sem valor mágico no schema.
- **Já incluir captura de aceite (`accepted`) e recomendador ao vivo dentro da criação de sessão.**
  Deferida: mantém a fatia mínima e testável (simplicidade > complexidade prematura). `accepted`
  permanece nullable, pronto para a fatia de aceite.
- **Janela temporal para o evento adverso.** Deferida: por ora, o EA mais recente pesa (conservador
  para segurança); refinar a janela é evolução incremental.

## Consequências
- **Positivas:** o recomendador passa a funcionar ponta a ponta por **regras transparentes,
  versionadas e auditáveis**, dentro da biblioteca validada, sem vazar o braço e com `feature_vector`
  acumulando para pesquisa de ML **offline**. Suíte backend: 169 → **177 testes**; cobertura **87,2%**;
  `router.py`/`service.py` a 100%.
- **Custo/tradeoff (visão do analista):**
  - `recommender.py` fica com ~51% de cobertura porque `coherence_report` e o bloco de self-test
    `__main__` não são exercidos pela API — são utilitários **offline** (não entram no caminho ao vivo).
  - A associação banda↔estado é **convenção** da literatura, não eficácia comprovada — a resposta
    sempre carrega `evidence_note` + `disclaimer` (sem overclaim).
- **Pendências:** ~~captura de aceite/coerência~~ (ADR-069); ~~janela temporal do EA~~ e
  ~~`last_liked`/`last_intensity` da última pós-sessão~~ (feito — ver Complemento); consolidação
  offline do `recommendation_log` (fatia E4).

## Complemento (2026-07-09) — sinais vivos: janela do EA + tolerabilidade
Fecha dois refinamentos de segurança, **sem migração nem mudança de contrato** (só derivação no
servidor, em `build_input`):
1. **Janela do evento adverso** (`ADVERSE_WINDOW_DAYS = 14`): EAs mais antigos que a janela não
   de-escalonam mais (evita ficar preso para sempre num EA remoto).
2. **Guardrail de tolerabilidade ao vivo:** `last_liked`/`last_intensity` passam a vir da
   **pós-sessão mais recente** do participante (`liked` 0–4 → booleano por `LIKED_THRESHOLD = 2`).
   Sessão anterior intensa (≥4) e não tolerada → de-escalona (G2) + `flag_review`.
+3 testes (EA fora da janela não de-escalona; baixa tolerabilidade de-escalona; sessão tolerada
segue a regra normal); suíte 187 → **190**, cobertura 87,9%. Continua tudo no servidor, sem vazar o braço.

## Conformidade
CI verde exige `tests/test_recommender_api.py`: objetivo→banda (ansiedade→alfa, sono/onset→teta);
guardrails **resolvidos no servidor** (EA moderado recente → de-escalona + `flag_review`; triagem
inelegível → `no_recommendation` com protocolo NULL registrado); **não vazamento** (braços opostos
recebem mesma forma e mesmo handle; nenhum termo de condição na resposta); e negações (401 sem token,
403 para staff sem `recommend:read`, 422 para `goal` inválido). Invariante preservada: toda
recomendação (`action = recommend`) fica **dentro da biblioteca validada** (assert no motor).
