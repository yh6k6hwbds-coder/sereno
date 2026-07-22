# ADR-090 — Endurecimento operacional: freio no endpoint público, rotação da chave de assinatura, prontidão real e registro de login

- **Status:** Aceito
- **Data:** 2026-07-21
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança), 1 (arquitetura/infra)
- **Contexto de origem:** **pendências anotadas dentro de fatias já fechadas** — ADR-082 ("rate
  limit no endpoint público; rotação da chave de assinatura"), ADR-080 ("`/ready` real") e ADR-081
  ("registro do `last_login_at`"). Nenhuma delas expande escopo; todas são dívida do MVP.
- **Relaciona-se com:** ADR-082 (entrega de áudio por URL assinada), ADR-064/078/079 (rate limit,
  IP real, política de falha do Redis), ADR-080 (métricas), ADR-081 (lifecycle de staff),
  ADR-087 (rotação de chave por convivência ativa/aposentada).

## Contexto

Com as Fases A–E fechadas, o que restava de código eram quatro pontas soltas — cada uma
registrada como "pendência" no ADR da fatia que a criou, e nenhuma coberta por teste:

1. **`GET /v1/audio/{content_hash}` é o único endpoint sem `Authorization`** (a capability é a
   assinatura, como num presign de nuvem). Ele nascera **sem rate limit**: qualquer um podia varrer
   assinaturas ou puxar áudio indefinidamente, sem freio. O limite existia só onde havia senha/OTP
   (ADR-064) — exatamente onde o abuso é menos barato.
2. **A chave de assinatura não podia ser trocada.** Havia uma chave só; rotacioná-la invalidaria
   **na hora** toda URL já entregue — derrubando a sessão de quem estivesse ouvindo. Na prática, a
   chave nunca seria trocada, que é o pior desfecho possível para uma chave.
3. **`/ready` mentia.** Era `return {"status": "ready"}` fixo, com um `# TODO`. Durante uma queda de
   banco a réplica seguia se declarando pronta e o roteador continuava mandando tráfego para quem só
   sabia devolver 500. Uma sonda que sempre diz "sim" é pior que sonda nenhuma: dá falsa garantia.
4. **`last_login_at` nunca era escrito.** A coluna existe (ADR-081) e a lista de staff a exibe —
   sempre vazia. Um campo de segurança que ninguém preenche vira ruído: o revisor olha "último
   acesso: —" e conclui a coisa errada sobre uma conta.

## Decisão

1. **Rate limit no endpoint público, ANTES da verificação da assinatura.** `rate_limit(bucket="audio",
   default_limit=60/min por IP)`, reusando a porta existente (ADR-064, IP real por ADR-078, postura
   de falha por ADR-079). A ordem é deliberada: aplicar o freio **antes** do `verify_signed` faz com
   que ele valha também para quem só varre assinaturas — se viesse depois, a força-bruta do HMAC
   ganharia tentativas ilimitadas (403 é barato) e o limite puniria apenas o uso legítimo.
   Configurável por `AUDIO_RATE_LIMIT`/`AUDIO_RATE_WINDOW_S`. O 429 tem a **mesma forma para os dois
   braços** (teste guarda) — um freio que respondesse diferente por condição vazaria o cegamento.
2. **Rotação da chave de assinatura, na mesma forma do `keyring` da PII (ADR-087).** A chave **ativa**
   (`AUDIO_URL_SIGNING_KEY`) é a única que **assina**; chaves **anteriores**
   (`AUDIO_URL_SIGNING_KEYS_PREVIOUS`, separadas por vírgula) seguem aceitas só para **verificar**.
   A janela de convivência é o próprio TTL da URL (minutos); passado ele, remove-se a anterior e as
   URLs velhas morrem. A verificação **não faz short-circuit** — todas as candidatas são comparadas
   em tempo constante, para não temporizar qual chave casou. Rotação **não estende validade**:
   assinatura expirada continua expirada (teste guarda).
3. **`/ready` sonda de verdade, e a sonda é limitada no tempo.**
   - **Banco (obrigatório):** `SELECT 1` **na sessão da própria requisição** (`Depends(get_db)`).
     Sondar uma engine à parte atestaria uma conexão que nenhum endpoint usa. Falhou → **503**.
   - **Redis (opcional, só com `REDIS_URL`):** `PING`, com peso **herdado do ADR-079** — com
     `SECURITY_FAIL_OPEN` (padrão) a queda do Redis não derruba login/OTP, logo também **não** pode
     tirar a réplica de serviço: reporta `degraded` e segue **pronta**. Com `SECURITY_FAIL_OPEN=0`
     a app recusaria tudo, então declarar-se pronta seria mentir → **não pronta**.
   - **`connect_timeout` curto na engine** (`DB_CONNECT_TIMEOUT_S`, padrão 5s). Banco inalcançável na
     rede (pacote **descartado**, não recusado) não devolve erro: pendura pelo default do SO, que é
     de minutos. Descoberto na prática — a primeira versão desta sonda **travou a suíte por 7 min**.
     Sonda pendurada é pior que sonda que falha: o orquestrador estoura o próprio timeout e a
     requisição ainda segura um worker.
   - **Corpo agregado e sem segredo:** só nome da dependência e estado curto. Nunca o texto da
     exceção — a mensagem do driver costuma trazer a DSN inteira (usuário:senha@host). Teste guarda.
   - **`/health` continua liveness puro** (não toca em dependência): senão uma queda de banco viraria
     reinício em loop, que não conserta banco nenhum.
4. **`last_login_at` gravado em `/auth/mfa/verify`** — e só ali. É o único passo que concede **acesso
   pleno** (MFA é obrigatório, inegociável #6): senha correta sem 2º fator **não é** login. `refresh`
   também não conta — renovar não é voltar a entrar, e contá-lo faria uma sessão esquecida parecer
   atividade recente, estragando justamente o sinal que o campo existe para dar. Só o carimbo de
   tempo, sem PII.

## Alternativas consideradas

- **Rate limit depois da verificação da assinatura** (só para requisições válidas). Rejeitada:
  deixaria a varredura de assinatura sem freio — o abuso que mais importa aqui.
- **Rate limit por `content_hash` em vez de por IP.** Rejeitada: a biblioteca tem poucos protocolos e
  o hash é compartilhado por todos do mesmo braço — limitar por hash penalizaria um braço inteiro (e
  o padrão de 429 por braço **vazaria a alocação**). Por IP é neutro quanto à condição.
- **Rotação com `key_id` embutido na URL** (como o ciphertext da PII faz). Rejeitada: exporia qual
  chave assinou e cresce a superfície do que é público, sem ganho — verificar duas ou três chaves
  HMAC é barato e o TTL curto mantém a lista minúscula.
- **`/ready` reprovando na queda do Redis, sempre.** Rejeitada: contradiria o ADR-079. Com fail-open
  a app **funciona** sem Redis; tirar a réplica de serviço transformaria uma degradação prevista em
  indisponibilidade total — exatamente o que aquele ADR decidiu evitar.
- **Gravar `last_login_at` no `/auth/token`** (senha correta). Rejeitada: registraria como "login" um
  passo que não concede acesso, inflando o campo com tentativas que pararam no MFA.

## Consequências

**Positivas:** o único endpoint público deixa de ser canal ilimitado; a chave de assinatura passa a
ser **rotacionável de fato** (sem derrubar sessão em curso), o que é pré-requisito para responder a
incidente; `/ready` passa a informar o estado real e o roteador da Fly pode confiar nele; a lista de
staff ganha o dado de acesso que já prometia. **+16 testes** (suíte 281→297, cobertura 90%).

**Negativas / a vigiar:**
- O limite de 60/min por IP é generoso para o uso real (uma sessão baixa um arquivo + alguns Range),
  mas **NAT compartilhado** (laboratório/campus com vários participantes na mesma saída) conta como
  um IP só. Se aparecer 429 no piloto, subir `AUDIO_RATE_LIMIT` — não removê-lo.
- O `connect_timeout` de 5s vale para **toda** conexão nova ao Postgres, não só para a sonda. Em rede
  degradada isso troca "espera longa" por "erro rápido" — desejável, mas é mudança de comportamento.
- A rotação exige **disciplina operacional**: quem troca a chave precisa lembrar de remover a
  anterior depois do TTL. Manter a anterior indefinidamente anula metade do benefício da rotação.
- `last_login_at` é um dado de **acesso de staff** (não de participante, não é PII de pesquisa), mas
  entra no ROPA como registro operacional — anotar na próxima revisão do `registro-operacoes-tratamento.md`.

## Verificação

- `tests/test_readiness.py` (8): banco fora → 503 e `/health` segue 200; Redis fora → `degraded`+pronto
  (fail-open) vs não pronto (fail-closed); Redis ausente não é falha; corpo não vaza DSN/host/senha.
- `tests/test_audio_signed_url.py` (+6): 429 após o limite; **freio antes da verificação** (varredura
  de assinatura é limitada); 429 não vaza braço; URL emitida antes da troca segue válida com a chave
  anterior declarada e morre quando ela é aposentada; a anterior **nunca assina**; rotação não estende
  validade.
- `tests/test_auth.py` (+2): `last_login_at` nasce vazio, não é preenchido por senha-sem-MFA nem por
  `refresh`, e é gravado no `mfa/verify`; MFA falho não registra login.
- CI-espelho verde: 297 testes / 90%, migração SQLite (nenhuma nova — sem mudança de schema),
  OpenAPI válido, bateria FFT (4) aprovada.
