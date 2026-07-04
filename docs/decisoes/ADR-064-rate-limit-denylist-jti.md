# ADR-064 — Rate limiting por IP + denylist de token por `jti`

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Fatia D2 do ROADMAP (endurecimento de autenticação)
- **Relaciona-se com:** ADR-043 (auth staff), ADR-047 (auth participante/OTP), ADR-028 (JWT)

## Contexto
Os ADR-043/047 deixaram pendentes duas defesas: **limitar a taxa** de `request-otp` e `login`
(força-bruta/abuso/enumeração) e **revogar tokens** antes de expirar (logout/incidente). Os
JWT já carregam `jti`, então a revogação é viável sem mudar o formato do token.

## Decisão
1. **Rate limiting por IP** em `POST /auth/participant/request-otp` e `POST /auth/token`, com
   **janela fixa** configurável por ambiente (`<BUCKET>_RATE_LIMIT`, `<BUCKET>_RATE_WINDOW_S`).
   Estoura → **429** em problem+json. No login, o limite é aplicado **antes** da verificação de
   senha, então tentativas erradas também contam (é o ponto da defesa).
2. **Denylist de token por `jti`:** `current_user` recusa um access token cujo `jti` esteja
   revogado; `POST /auth/refresh` recusa refresh revogado. `POST /auth/logout` (autenticado)
   revoga o `jti` do access apresentado e, se enviado, o do `refresh_token` — cada um com TTL =
   tempo restante do próprio token (não mais que isso).
3. **Portas com duas implementações:** `RateLimiter` e `TokenDenylist` têm impl **em memória**
   (dev/teste, um processo) e **Redis** (produção, via `REDIS_URL`). Só o Redis vale entre
   múltiplos workers — em produção multi-worker é obrigatório.

## Alternativas consideradas
- **Middleware global de rate limit.** Rejeitada: só os endpoints sensíveis precisam agora;
  mirar neles é mais simples e não penaliza o tráfego autenticado normal.
- **Janela deslizante / token bucket.** Adiada: janela fixa é suficiente e trivial de raciocinar
  no piloto; dá para trocar atrás da porta se necessário.
- **Denylist em banco (tabela).** Rejeitada: TTL/expiração e velocidade casam com Redis/memória;
  no banco somaria carga de escrita e um job de limpeza.
- **Só TTL curto, sem denylist.** Rejeitada: não permite revogar em logout/incidente antes do exp.

## Consequências
- **Positivas:** OTP/login protegidos contra abuso; sessão revogável de verdade (logout); base
  para revogação em incidente. Suíte: 87 → 93 testes. Fecha a pendência dos ADR-043/047.
- **Custo/tradeoff (visão do analista):**
  - **Estado não compartilhado** nas impls em memória: em produção com vários workers, **sem
    `REDIS_URL` o limite/revogação valem só por processo** (defesa enfraquecida). Precisa de Redis.
  - **IP do cliente = `request.client.host`:** atrás de proxy/balanceador isso é o IP do proxy —
    todos os usuários compartilhariam um bucket. Produção deve tratar `X-Forwarded-For` com proxy
    **confiável** (senão vira limite global). **Pendência explícita** antes de expor publicamente.
  - **Falha do Redis:** hoje um Redis indisponível faria as chamadas levantarem (→ 500). Decidir
    **fail-open vs fail-closed** por endpoint é pendência (login talvez fail-closed; OTP idem).
  - **Logout revoga só os tokens apresentados:** um refresh roubado e não apresentado continua
    válido até expirar; "revogar tudo do usuário" (versão/época por usuário) fica como futuro.
- **Pendências:** confiança de proxy/`X-Forwarded-For`; política de falha do Redis; revogação em
  massa por usuário; rotação/limpeza de chaves de rate limit.

## Conformidade
CI verde exige `tests/test_throttle.py`: `request-otp` e `login` retornam **429** após o limite
(erro de senha conta); dentro do limite segue normal; **logout revoga o access** (mesmo token →
401) e o **refresh** enviado (→ 401 no `/auth/refresh`); logout exige autenticação (401 sem
token). O isolamento do estado entre testes é garantido por fixture autouse no `conftest`.
