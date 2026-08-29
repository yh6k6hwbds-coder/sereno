# ADR-092 — Entrega de e-mail durável (fila RQ/Redis) e distinção de bounce

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** item **F4.5** do `docs/ROADMAP.md` ("adaptador RQ/Redis para e-mail
  (durabilidade) + bounces"), autorizado explicitamente pelo mantenedor — é construção pós-piloto,
  fora do MVP por escopo.
- **Relaciona-se com:** ADR-085 (porta `EmailDelivery`), ADR-063 (OTP), ADR-080 (métricas),
  ADR-077 (guard de produção), F3.2 (SMTP real, ainda pendente de credencial).

## Contexto

O ADR-085 desacoplou o **envio** do caminho da requisição e deixou a porta `EmailDelivery` com dois
adaptadores: `inline` (síncrono) e `background` (thread pool). Ele mesmo registrou a fila RQ/Redis
como "o próximo adaptador desta mesma porta". Duas lacunas justificam construí-lo agora:

1. **Durabilidade.** No `background`, a mensagem vive na memória de um `ThreadPoolExecutor`. Um
   deploy, um restart ou um OOM no meio do envio a perde **sem deixar rastro além do contador**.
   Para o OTP isso é direto: o participante pede o código, recebe `200`, e nada chega — ele não tem
   como distinguir isso de um e-mail atrasado, e o suporte do piloto é uma pessoa só.
2. **Bounce ≠ falha transitória.** O `SmtpEmailSender` reintentava **tudo** 3 vezes com backoff,
   inclusive `550 mailbox unavailable`. Insistir num endereço que não existe não muda o desfecho,
   queima a janela de validade do OTP e prejudica a reputação do remetente — que, num domínio novo
   de instituição, é o ativo mais frágil do envio. Pior: os dois casos caíam no **mesmo** contador
   `failed`, então nenhum alerta conseguiria dizer "o SMTP está fora" versus "esse endereço está
   errado" — que exigem ações opostas (esperar × falar com a pessoa).

## Decisão

1. **`QueueDelivery`** — terceiro adaptador da porta `EmailDelivery`, ativado por
   `EMAIL_DELIVERY=queue` (aliases `rq`/`redis`). Enfileira `send_email_job` numa fila **RQ** sobre
   o Redis já existente; o request retorna sem tocar em SMTP e o job sobrevive a restart/deploy.
2. **Worker separado: `backend/scripts/email_worker.py`** (`--burst` para drenar e sair), que roda
   `Worker.work(with_scheduler=True)` — **sem o scheduler os jobs de retry agendados nunca voltam
   para a fila**, e a durabilidade seria só aparente.
3. **`PermanentEmailError` + `is_permanent_failure()`** — classificação explícita: `5xx` e
   destinatário recusado com `5xx` são **definitivos**; `4xx`, erro de rede e exceção **sem** código
   são **transitórios**. O padrão em caso de dúvida é *transitório*: descartar um OTP por engano
   trava o participante, enquanto uma tentativa extra custa pouco.
4. **Terceiro desfecho na métrica: `bounced`** (`emails_total{outcome=...}` passa a ser
   `sent|failed|bounced`). Continua sem destinatário, assunto ou corpo — só o desfecho.
5. **O `SmtpEmailSender` não reintenta bounce**: para na primeira tentativa e levanta
   `PermanentEmailError`. Transitório segue com os 3 retries e backoff de antes.
6. **O job repropaga o transitório e engole o bounce.** `_send_and_observe(..., reraise_transient=True)`
   só no worker: repropagar é o que faz o RQ reintentar mais tarde (10 s → 60 s → 300 s). No caminho
   da API o comportamento best-effort de antes é preservado — nenhuma rota passa a poder falhar por
   causa de e-mail.
7. **Corpo do OTP não fica parado no Redis.** O job carrega o corpo (o código em claro só existe ali;
   no banco há apenas o hash — ADR-063). Por isso `ttl=EMAIL_JOB_TTL` (10 min, a ordem de grandeza da
   validade do OTP), `result_ttl=0` e **`failure_ttl=0`**: nada de job morto guardando código em
   registro de falha. O desfecho continua observável pela métrica, que não carrega corpo.
8. **Redis fora → entrega inline naquela mensagem.** Falha ao enfileirar não pode travar
   `request-otp`; melhor tentar enviar agora do que perder o código em silêncio.
9. **`EMAIL_DELIVERY=queue` sem `REDIS_URL` falha explícito.** Cair calado para `inline` daria a
   falsa impressão de durabilidade — exatamente o tipo de engano que só aparece no dia do incidente.
10. **O guard de produção vale no worker também** (`validate_runtime_config()` no boot): um worker
    com `EMAIL_DEV_CONSOLE` ligado imprimiria o OTP no log do worker (inegociável #6).
11. **Log sem PII:** o endereço vira `***@dominio` (`mask_recipient`). O domínio é o que torna um
    bounce acionável — domínio inteiro recusando é problema de configuração, caixa isolada é
    endereço errado — e não identifica ninguém.
12. **Sem mudança de contrato nem de schema.** Nenhum endpoint novo, nenhuma migração.

## Alternativas consideradas

- **Manter só o `background` e aumentar os retries.** Rejeitada: mais retries não resolvem perda por
  restart, que é o modo de falha que importa num deploy.
- **Tabela de outbox no Postgres** (job durável no próprio banco). Rejeitada **por ora**: seria mais
  auditável e dispensaria o Redis, mas exige migração, polling e um segundo mecanismo de expurgo —
  e colocaria o **código do OTP em claro no banco**, que hoje só guarda o hash. Pior troca de
  privacidade que a fila com TTL curto.
- **Serviço de e-mail transacional com webhook de bounce** (SES/SendGrid). Rejeitada agora: depende
  de contratação e de mais um operador no ROPA/DPA (F1.4). A classificação por código SMTP cobre o
  caso do piloto sem novo terceiro.
- **Marcar o contato como "não entregável" no banco ao receber bounce.** Rejeitada nesta fatia:
  mexeria em `contact_info` (PII cifrada) e criaria um estado que ninguém no piloto tem processo para
  tratar. O alerta do F4.6 leva a informação a um humano, que é o que existe hoje.

## Consequências

**Positivas:** a entrega deixa de depender da memória do processo; bounce e queda de SMTP viram
sintomas distintos e alertáveis (insumo direto do F4.6); o endereço sai dos logs; nenhum caminho de
request passa a poder falhar por e-mail. **+10 testes** (suíte 307→317).

**Negativas / a vigiar:**
- **A durabilidade só existe se alguém rodar o worker.** Como no ADR-091, o mecanismo está pronto e
  o passo operacional não: `EMAIL_DELIVERY` segue em `inline` por padrão e o modo `queue` só entra em
  uso quando houver processo de worker no deploy (F3.3) e SMTP real (F3.2).
- **O corpo do OTP transita pelo Redis.** Mitigado por TTL curto e por não reter job morto, mas é uma
  superfície nova: exige Redis com credencial e TLS no ambiente de produção, e uma linha no ROPA
  quando o modo `queue` for ativado de fato.
- A classificação por código SMTP é heurística de provedor: alguns devolvem `550` para greylisting
  agressivo. Se aparecer, o ajuste é em `is_permanent_failure()`, não espalhado pelo código.

## Verificação

`tests/test_email_delivery.py` (18, sendo 10 novos): classificação 5xx/4xx/sem-código; bounce conta
`bounced` e não `failed`; bounce **não** é reintentado (1 tentativa) e transitório ainda é (3);
`QueueDelivery` enfileira em vez de enviar, com `ttl`/`result_ttl`/`failure_ttl` corretos; Redis fora
cai para inline; o job repropaga transitório e engole bounce; `queue` sem `REDIS_URL` levanta; o log
traz `***@dominio` e não o endereço; endereço sem `@` some por inteiro.
