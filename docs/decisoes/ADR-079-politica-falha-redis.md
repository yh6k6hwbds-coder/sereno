# ADR-079 — Política de falha do Redis (rate limit / denylist): fail-open por padrão

- **Status:** Aceito
- **Data:** 2026-07-14
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Pendência explícita do ADR-064 ("política de falha do Redis")
- **Relaciona-se com:** ADR-064 (rate limit + denylist), ADR-078 (IP real do cliente)

## Contexto
O ADR-064 pôs o rate limit (`RedisRateLimiter`) e a denylist de `jti` (`RedisDenylist`)
atrás de Redis em produção, mas deixou **sem definição** o que acontece quando o Redis está
indisponível. Na prática, qualquer operação (`incr`/`expire`/`exists`/`set`) levantava exceção
**não tratada** → **500**. Como esses caminhos cobrem `request-otp`, `login` e a verificação de
revogação em **toda rota autenticada**, um blip de Redis derrubaria a autenticação inteira do
piloto. Precisava-se de uma degradação previsível.

## Decisão
1. **Postura única e configurável** por `SECURITY_FAIL_OPEN` (helper `config.security_fail_open()`),
   **padrão `fail-open`** — adequado a um piloto de N≈40, onde disponibilidade pesa mais que a
   janela de abuso durante uma falha rara, e os tokens de acesso têm TTL curto.
2. **Rate limit** (`RedisRateLimiter.hit`): Redis fora → **deixa passar** (fail-open) ou **bloqueia**
   (fail-closed, 429), conforme a postura. Um limitador não deve virar ponto único de falha.
3. **Denylist** (`RedisDenylist.is_revoked`): Redis fora → trata o token como **não revogado**
   (fail-open, segue) ou **revogado** (fail-closed, 401), conforme a postura.
4. **`revoke()` é best-effort**: uma falha ao gravar (logout) **não** propaga exceção — o logout
   responde normalmente e o token ainda expira por TTL. (Não há "fail-closed" sensato para uma
   escrita; registrar e seguir é o correto.)
5. Toda degradação emite **log de aviso estruturado** (`logger sereno.security`) com o tipo do
   erro e a postura — **sem PII, sem jti, sem braço** — para a operação enxergar a falha.

## Alternativas consideradas
- **Fail-closed por padrão.** Rejeitada para o piloto: um blip de Redis tiraria login/OTP e toda
  rota autenticada do ar. Continua disponível via `SECURITY_FAIL_OPEN=0` para quem priorizar defesa.
- **Postura por endpoint** (ex.: login fail-closed, resto fail-open). Rejeitada por ora: mais
  superfície e configuração para um ganho marginal no piloto; dá para refinar atrás do helper.
- **Circuit breaker / cache local de fallback.** Adiada: complexidade desproporcional ao risco
  atual (Redis só é obrigatório em multi-worker; hoje o piloto roda em 1 máquina).

## Consequências
- **Positivas:** sem 500 por indisponibilidade de Redis; degradação previsível e observável;
  a escolha de risco fica explícita e reversível por env. Suíte: 200 → 206 testes.
- **Custo/tradeoff:** no padrão fail-open, durante uma queda de Redis o rate limit não protege e
  um token revogado ainda vale até o TTL — janela pequena e registrada. Quem exigir postura de
  defesa estrita usa `SECURITY_FAIL_OPEN=0` (aceitando indisponibilidade sob falha de Redis).
- **Pendências:** postura por endpoint e circuit breaker, se e quando o volume justificar.

## Conformidade
CI verde exige `tests/test_redis_failure.py`: com o backend fora, rate limit **deixa passar** no
padrão e **bloqueia** com `SECURITY_FAIL_OPEN=0`; denylist trata o token como **não revogado** no
padrão e **revogado** com fail-closed; `revoke()` **não** propaga exceção; a degradação **loga um
aviso**. Nenhuma decisão inegociável é tocada (sem PII/braço em log; escopo do piloto preservado).
