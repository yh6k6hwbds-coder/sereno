# ADR-083 — Pipeline de features para ML, offline e cego (consolidação do recommendation_log)

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 6 (recomendador), 7 (análise), Fase E (E4)
- **Contexto de origem:** ROADMAP E4 — "consolidar recommendation_log/telemetria para pesquisa de
  modelos, sempre offline".
- **Relaciona-se com:** inegociável #5 (recomendador por regras; ML nunca decide ao vivo; guarda
  `feature_vector` para ML futuro), inegociável #2 (alocação oculta), inegociável #6 (PII/LGPD),
  ADR-068/069 (recomendador + `recommendation_log`), ADR-066 (export pseudonimizado C6)

## Contexto
Desde o ADR-068 cada recomendação grava, no `recommendation_log`, o `feature_vector` da entrada,
a regra disparada, a saída (handle neutro) e — via ADR-069 — o aceite e o vínculo com a sessão.
O inegociável #5 diz explicitamente que esse vetor é guardado "para um ML **futuro**". Faltava a
peça que a E4 pede: **consolidar** esse log + a telemetria de sessão num **dataset de pesquisa**
utilizável para modelagem, **sem** abrir qualquer porta para ML decidir ao vivo. O CLAUDE.md marca
ML como fora do MVP; por isso esta fatia entrega **só a consolidação offline** (endossada pelo #5),
não treino/inferência.

## Decisão
1. **`GET /v1/research/ml-features`** (RBAC `export:request`, o mesmo gate do export clínico C6):
   devolve um **CSV** com **uma linha por recomendação**, achatando o `recommendation_log` +
   (quando vinculada) a telemetria da sessão e a pós-sessão. `features_service.py`.
2. **Sempre OFFLINE (inegociável #5):** o endpoint **apenas lê e consolida** o que já foi
   registrado — não cria recomendação, não chama o motor, não decide nada. Um teste guarda que
   duas leituras não alteram a contagem de `recommendation_log`.
3. **Pseudonimizado, sem PII (inegociável #6):** só o `study_code`; **nenhuma hora de parede** —
   a ordem temporal entra como **índice ordinal por participante** (`rec_index`), que é feature
   sem ser identificador. Auditado (`features.exported`) com meta neutra (só o nº de linhas).
4. **Cego, sem a condição (inegociável #2):** jamais ativo/sham nem a chave selada — apenas o
   braço **CODIFICADO A/B** (`Grupo A`/`Grupo B`, ou `nao_alocado`), como no C6. O
   `protocolo_sugerido` é o **handle neutro de banda** (ex.: `alpha-10`), que não revela braço.
5. **Cobertura completa dos eventos:** incluem-se as `no_recommendation` dos guardrails (evento de
   segurança) e as recomendações **ainda não vinculadas** a uma sessão (telemetria em branco) —
   ausência é informativa e não vira 0.
6. **Sem migração:** lê tabelas existentes; nada de schema novo.

## Alternativas consideradas
- **Endpoint que treina/serve um modelo.** Rejeitada: viola o inegociável #5 e o escopo (ML fora
  do MVP). Esta fatia para **antes** de qualquer inferência — só materializa o dataset.
- **Emitir timestamps crus por evento.** Rejeitada: minimização de re-identificação; o `rec_index`
  ordinal preserva a ordem (a feature real) sem expor a hora de parede.
- **Incluir a condição (ativo/sham) "porque é offline".** Rejeitada: quebraria o cegamento
  (inegociável #2) e o *data lock*; o braço codificado A/B basta para pesquisa cega, como no C6.
- **Job assíncrono (como o C6).** Adiada: N do piloto é pequeno; um `GET` síncrono é o slice
  completo mais simples (CLAUDE.md: "simplicidade suficiente > complexidade prematura"). A
  consolidação por job offline (RQ) + storage fica como pendência de produção.

## Consequências
- **Positivas:** o `feature_vector` que o #5 mandou guardar agora vira **dataset consolidado** para
  pesquisa de modelos, sem tocar no caminho de decisão ao vivo. Reúsa o gate/estilo do C6. Suíte
  234 → 241 (+7). Sem migração (fatia leve).
- **Custo/tradeoff:** a serialização roda **inline** no request (como o C6 pré-job); para volumes
  maiores migra para job offline. O dataset é **wide** (uma linha por recomendação, com telemetria
  repetida quando há vínculo) — suficiente para o piloto; normalização fica para o consumo.
- **Pendências:** consolidação por job offline (RQ) + storage/URL assinada; features derivadas
  (ex.: agregados por participante); versionar o **schema do dataset** quando a modelagem começar.

## Conformidade
CI verde exige `tests/test_ml_features.py`: só `export:request` baixa (participante 403, anônimo
401); uma linha por recomendação incluindo `no_recommendation` e recomendações sem sessão (telemetria
em branco); telemetria presente quando há sessão+pós-sessão vinculadas; pseudonimizado e **cego**
(só `Grupo A/B`, nenhum termo de condição; `protocolo_sugerido` neutro); export **auditado** sem
PII/braço (só nº de linhas); **offline** (consolidar não cria recomendação). Sem segredo versionado;
sem PII/braço em log; inegociáveis #2/#5/#6 preservados.
