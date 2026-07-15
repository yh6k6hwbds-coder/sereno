# ADR-080 — Métricas de observabilidade (Prometheus) sem PII nem alta cardinalidade

- **Status:** Aceito
- **Data:** 2026-07-14
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/observabilidade)
- **Contexto de origem:** Pendência explícita do ADR-067 ("Métricas ficam pendentes")
- **Relaciona-se com:** ADR-067 (logs JSON sem PII/braço), ADR-076 (deploy Fly.io)

## Contexto
O ADR-067 entregou logs JSON estruturados (sem PII nem braço) mas deixou **métricas** como
pendência. Sem métricas agregadas, não dá para ver volume de tráfego, taxa de erro (4xx/5xx)
nem latência por endpoint durante o piloto — sinais operacionais básicos para saber se a API
está saudável e se os participantes conseguem completar os fluxos. O deploy é na Fly.io
(ADR-076), cujo Prometheus gerenciado **raspa um endpoint `/metrics`** pela rede privada.

## Decisão
1. **Formato Prometheus** exposto em `GET /metrics` (`core/metrics.py`), o padrão que a Fly (e
   Grafana) já consomem — sem inventar formato próprio. Lib madura `prometheus-client`.
2. **Duas séries, rótulos de baixa cardinalidade:** `http_requests_total{method,path,status}`
   (Counter) e `http_request_duration_seconds{method,path}` (Histogram). O `path` é o **template
   da rota** (ex.: `/sessions/{session_id}/audio`), **nunca** o caminho concreto — um UUID no
   caminho explodiria a cardinalidade e não agregaria nada. Rotas não casadas (404) colapsam em
   `<unmatched>` — defesa contra cardinalidade dirigida por atacante.
3. **Sem PII, sem braço:** só método/template/status; nenhum corpo, identificador em claro ou
   condição (ativo/sham). Registro **dedicado** (`CollectorRegistry`), sem coletores de processo.
4. **Instrumentação no middleware** que já existia para o log (ADR-067): uma passagem mede as
   duas coisas. O log mantém o caminho **concreto** (útil p/ depurar, UUID pseudônimo é aceito
   pelo ADR-067); a métrica usa o **template**. O próprio `/metrics` não se auto-mede.
5. **Guard opcional:** se `METRICS_TOKEN` estiver setado, `/metrics` exige `Authorization:
   Bearer <token>` (defesa em profundidade). Sem ele (padrão), o endpoint é aberto — aceitável
   porque só expõe agregados. O `fly.toml` liga `[metrics]` para o scraping nativo da Fly.

## Alternativas consideradas
- **`prometheus-fastapi-instrumentator`.** Rejeitada: traz mais superfície/config do que o
  necessário; um middleware de ~10 linhas sobre `prometheus-client` cobre o caso do piloto.
- **Formato JSON próprio / StatsD.** Rejeitada: Prometheus é o que a plataforma-alvo raspa; um
  formato próprio exigiria um coletor sob medida.
- **Rótulo pelo caminho concreto.** Rejeitada: cardinalidade ilimitada (UUIDs) e risco de expor
  identificadores nas séries. Template é a prática correta.
- **`/metrics` sempre autenticado.** Rejeitada como padrão: o scraper nativo da Fly não envia
  auth; deixamos o token como opt-in (com a ressalva de trocar de coletor se ligado).

## Consequências
- **Positivas:** volume, taxa de erro e latência por endpoint visíveis no piloto; integra com o
  Prometheus/Grafana da Fly sem cola extra; instrumentação barata (reusa o middleware). Suíte:
  206 → 213 testes. Fecha a pendência do ADR-067.
- **Custo/tradeoff:** nova dependência (`prometheus-client`, madura). O template é **relativo ao
  mount** — o prefixo constante `/v1` não entra no rótulo (não distingue endpoints; cada router
  mantém seu prefixo, sem colisão). `/metrics` público por padrão expõe só agregados; quem exigir
  sigilo usa `METRICS_TOKEN`.
- **Pendências:** métricas de negócio (ex.: sessões completas/dia) e alertas ficam para quando o
  piloto pedir; readiness real (`/ready` ainda é stub) é item à parte.

## Conformidade
CI verde exige `tests/test_metrics.py`: `/metrics` responde no formato Prometheus e reflete o
tráfego (contador de `/health` incrementa); o rótulo é o **template** e o **UUID concreto não
aparece**; rota inexistente vira `<unmatched>`; `/metrics` não se auto-mede; com `METRICS_TOKEN`,
exige Bearer (401 sem); nenhuma série expõe condição do estudo. Sem PII/braço (ADR-067 preservado).
