# ADR-067 — Observabilidade sem PII + CI endurecido

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/infra), 3 (cliente)
- **Contexto de origem:** Fatia D5 do ROADMAP
- **Relaciona-se com:** ADR-026 (PII), ADR-052 (cegamento no cliente), ADR-054 (widget tests)

## Contexto
Faltavam logs estruturados (para operar sem vazar PII/braço) e um CI que **realmente** cobrisse
o cliente e um piso de qualidade no backend. O job Flutter estava com `|| true` (não bloqueava).

## Decisão
1. **Logs estruturados (JSON)** em `core/logging.py`: um `JsonFormatter` e um middleware que
   registra apenas **método, caminho, status e latência** de cada requisição — **nunca** o corpo
   (que pode conter PII, OTP, senha) nem a condição (ativo/sham). Nível via `LOG_LEVEL`.
2. **CI endurecido:**
   - **Backend com piso de cobertura:** `pytest --cov=app --cov-fail-under=80` (hoje **84,67%**).
   - **Job `app` (Flutter) agora BLOQUEANTE:** removido o `|| true`; passos separados
     (`flutter pub get` · `flutter analyze` · `flutter test`).

## Alternativas consideradas
- **Logar o corpo/headers para depurar.** Rejeitada: risco de PII/OTP/senha em log; caminho com
  UUID pseudônimo já dá rastreabilidade suficiente.
- **Piso de cobertura mais alto (ex.: 90%).** Rejeitada por ora: 80% dá folga sob os 84,67% atuais
  sem travar mudanças pequenas; subir o piso é evolução incremental.
- **Manter o job Flutter não-bloqueante.** Rejeitada: é justamente o objetivo de D5 — agora há
  widget tests reais (A2), então o job deve **gate**.

## Consequências
- **Positivas:** operação observável sem vazar PII/braço; o CI passa a **cobrir o cliente** e a
  impor um piso de qualidade no backend. Suíte backend: 139 → 142 testes.
- **Custo/tradeoff (visão do analista):**
  - **Ponto de atenção honesto:** o job `app` agora **bloqueia** com base nos widget tests de A2,
    que foram **escritos mas não executados localmente** (sem SDK Flutter na máquina de dev). Se
    houver um bug de compilação/lógica no Dart, o CI ficará **vermelho** — é o sinal esperado para
    corrigir A2, não uma regressão introduzida às cegas. Recomenda-se rodar `flutter test` no
    primeiro CI e ajustar se necessário.
  - **Logs com IDs pseudônimos** no caminho: aceitável (pseudonimização), mas revisar se algum
    caminho novo trouxer dado sensível.
  - **Piso de cobertura** pode falhar num PR que reduza cobertura — comportamento desejado.
- **Pendências:** métricas (Prometheus/OpenTelemetry) e correlação por request-id; subir o piso de
  cobertura ao longo do tempo; alertas a partir dos logs.

## Conformidade
CI verde exige `tests/test_logging.py`: o `JsonFormatter` emite JSON válido com os campos; o log
de requisição traz método/caminho/status/latência e **nunca** o corpo (teste envia um valor
sensível e verifica que ele não aparece no log). O job backend falha se a cobertura cair abaixo de
80%; o job `app` falha se `flutter analyze`/`flutter test` falharem.
