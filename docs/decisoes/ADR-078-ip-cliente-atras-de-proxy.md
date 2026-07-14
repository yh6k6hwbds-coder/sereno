# ADR-078 — IP real do cliente atrás de proxy confiável (rate limit por cliente)

- **Status:** Aceito
- **Data:** 2026-07-14
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Pendência explícita do ADR-064 (endurecimento antes de expor publicamente)
- **Relaciona-se com:** ADR-064 (rate limit por IP + denylist), ADR-076 (deploy Fly.io)

## Contexto
O ADR-064 aplica rate limit **por IP** em `request-otp` e `login`, usando
`request.client.host`. Ele mesmo registrou a pendência: atrás de um proxy/borda, esse valor é
o IP do **proxy**, não do participante — todos cairiam em **um bucket global** e a defesa
contra força-bruta/abuso deixaria de valer. Com o deploy na Fly.io (ADR-076), o app passa a
ficar **sempre** atrás da borda da Fly, então a pendência virou defeito real antes de receber
participantes. O mesmo `request.client.host` também alimentava o `ip_address` gravado no
consentimento — que passaria a registrar o proxy, não quem consentiu.

Cabeçalhos de encaminhamento (`X-Forwarded-For`) são **falsificáveis pelo cliente**: confiar
neles ingenuamente troca um problema por outro (um atacante forja o IP e escapa do limite).

## Decisão
1. Um único ponto de resolução, `core/client_ip.py::client_ip(request)`, consumido pelo rate
   limit e pelo registro de IP do consentimento. A confiança em cabeçalhos é **opt-in** e
   explícita por ambiente; o **padrão continua seguro** (`request.client.host`).
2. **`CLIENT_IP_HEADER`** (precedência): nome de um cabeçalho de **confiança única** que a
   plataforma injeta e **sobrescreve** (à prova de spoof). Na Fly é `Fly-Client-IP` — ligado no
   `fly.toml`. Quando definido e presente, é a fonte da verdade.
3. **`TRUSTED_PROXY_HOPS`** (fallback genérico, padrão `0`): nº de proxies confiáveis à frente.
   Aplica-se ao `X-Forwarded-For` montando a cadeia `[xff..., peer]` e tomando o cliente
   `hops+1` posições a partir do fim — **só as `hops` entradas mais à direita (nossos proxies)
   são confiáveis**; qualquer valor forjado pelo cliente fica à esquerda e é ignorado.
4. Sem nenhuma das duas variáveis (dev/sem proxy), usa o peer direto — o comportamento anterior.

## Alternativas consideradas
- **Confiar sempre no primeiro token do `X-Forwarded-For`.** Rejeitada: é o valor mais fácil de
  o cliente forjar; anula o rate limit.
- **`ProxyHeadersMiddleware`/`--forwarded-allow-ips` do uvicorn.** Rejeitada: reescreve
  `request.client` globalmente por faixa de IP de proxy — mais amplo do que o necessário e não
  cobre o `Fly-Client-IP`, que é o mecanismo à prova de spoof na plataforma-alvo.
- **Fixar `Fly-Client-IP` no código.** Rejeitada: acopla o backend à Fly; `CLIENT_IP_HEADER` +
  `TRUSTED_PROXY_HOPS` mantêm a portabilidade (o `fly.toml` é quem escolhe a Fly).

## Consequências
- **Positivas:** o rate limit de OTP/login volta a valer **por cliente real** atrás da borda;
  o `ip_address` do consentimento passa a ser o do participante; resolução centralizada e
  testada (incl. resistência a spoof). Suíte: 190 → 200 testes. Fecha a pendência do ADR-064.
- **Custo/tradeoff:** exige **configurar** a plataforma corretamente (`CLIENT_IP_HEADER` na Fly;
  `TRUSTED_PROXY_HOPS` em outro proxy). Config errada (hops a mais/a menos) degrada para um IP
  vizinho na cadeia — mais conservador que vazar o limite, mas a ser conferido por plataforma.
- **Pendências (herdadas do ADR-064, não fechadas aqui):** política de falha do Redis
  (fail-open vs fail-closed); revogação em massa por usuário.

## Conformidade
CI verde exige `tests/test_client_ip.py`: sem config, `X-Forwarded-For` é **ignorado** (usa o
peer); `CLIENT_IP_HEADER` tem precedência e ignora XFF forjado; com `TRUSTED_PROXY_HOPS`, uma
entrada **forjada** à esquerda do XFF é descartada; e — integração — dois clientes reais atrás
do mesmo proxy recebem **buckets de rate limit separados**, enquanto sem proxy confiável
compartilham o bucket. Nenhuma decisão inegociável é tocada (sem PII/braço em log; escopo do
piloto preservado).
