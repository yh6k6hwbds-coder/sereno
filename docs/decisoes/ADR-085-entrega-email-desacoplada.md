# ADR-085 — Entrega de e-mail desacoplada do request (porta) + observabilidade de desfecho

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança/observabilidade)
- **Contexto de origem:** pendência pré-piloto "SMTP real" + a pendência aberta do D1 (ADR-063):
  "fila assíncrona (RQ/Redis, ADR-031) para desacoplar latência/falha".
- **Relaciona-se com:** ADR-063 (`EmailSender` — provedor SMTP/Null/Console/Memory), ADR-080
  (métricas Prometheus sem PII/braço), ADR-064 (rate limit no `request-otp`), inegociável #6
  (nunca logar o código/PII).

## Contexto
O `SmtpEmailSender` (ADR-063) já envia de verdade (STARTTLS/SSL, retries, sem logar o corpo).
O que faltava para ser **produção-seguro** não era o provedor, e sim **como ele é chamado**:
`deliver_otp` e `notify_team` faziam o `send()` **síncrono, dentro do thread do request**. Com
retries + `sleep` + timeouts de socket (10 s cada), um provedor lento ou fora **bloqueia** o
`request-otp` — endpoint **público** e alvo de abuso (mesmo com rate limit, segurar o thread é
vetor de DoS) — e o relato de **evento adverso (P0)**, que jamais pode atrasar por causa de e-mail.
Pior: a falha final era **engolida** pelos chamadores (`except Exception: return`), então uma
entrega perdida após os retries era **silenciosa** — ninguém sabia que o participante ficou sem OTP.

## Decisão
1. **Porta `EmailDelivery`** (`core/email.py`), separando *enfileirar* de *enviar*:
   - `InlineDelivery` (**padrão**): envia de forma síncrona — comportamento de dev/teste
     **inalterado** (determinístico; os testes leem o `outbox` na hora).
   - `BackgroundDelivery`: envia num `ThreadPoolExecutor` pequeno (daemon); o request **retorna
     na hora**, sem esperar o SMTP. Adequado ao deploy single-instance da Fly (ADR-076), **sem**
     exigir Redis/worker. Selecionável por `EMAIL_DELIVERY=background` (`EMAIL_WORKERS`, padrão 2).
   - A fila **RQ/Redis** (ADR-031) é o próximo adaptador desta mesma porta — a "construção" para
     escala/durabilidade, não necessária no piloto.
2. **Desfecho observável (fim da perda silenciosa):** todo envio passa por `_send_and_observe`,
   que conta `emails_total{outcome=sent|failed}` (ADR-080) e, na falha, loga um aviso **sem o
   corpo/código**. A métrica agrega só o desfecho — nunca destinatário, assunto ou o OTP.
3. **Best-effort de verdade:** a entrega **nunca propaga** — nem no inline nem no worker. Os
   chamadores deixam de ter `try/except` em volta do envio (a porta cuida da falha); o
   `deliver_otp` mantém o `try/except` **só** na decifragem da PII (sem chave/contato não há o quê
   enviar), que é trabalho de request, não de entrega.
4. **Sem mudança de contrato:** é comportamento interno de entrega + um contador no `/metrics`
   já existente. Sem migração.

## Alternativas consideradas
- **Manter síncrono e só robustecer.** Rejeitada: não resolve o bloqueio do request (DoS no
  `request-otp`, atraso no P0) — o problema é o acoplamento, não o provedor.
- **RQ/Redis já.** Rejeitada por ora: acopla o caminho crítico a infra que o deploy do piloto não
  tem (single-instance sem Redis, ADR-076) e contraria "não introduzir dependência pesada no
  caminho crítico" (CLAUDE.md). Fica como adaptador futuro da mesma porta.
- **Engolir a falha (status quo).** Rejeitada: perda silenciosa de OTP/alerta é inaceitável num
  piloto; o contador torna a falha visível sem vazar o código.
- **`asyncio` em vez de threads.** Rejeitada: o `smtplib` é bloqueante; um pool de threads é o
  encaixe simples e maduro sem reescrever o provedor.

## Consequências
- **Positivas:** `request-otp` e o relato de EA deixam de bloquear no SMTP (`background`); falhas
  de entrega viram sinal (`emails_total{outcome="failed"}`) em vez de silêncio; o provedor SMTP
  (ADR-063) fica inalterado atrás da porta. Suíte 249 → 257 (+8).
- **Custo/tradeoff:** no `background`, threads fazem I/O de SMTP; para o volume do piloto (N≈40,
  OTP esparso) um pool de 2 basta. Sem durabilidade — um restart perde envios em voo (aceitável no
  piloto; a fila RQ resolve quando precisar). O padrão segue **inline** para não mudar nada sem
  intenção explícita.
- **Pendências:** adaptador de fila **RQ/Redis** (durabilidade/escala); tratamento de **bounces**
  (provedor); alerta quando `emails_total{outcome="failed"}` subir (quando houver Alertmanager);
  segredo SMTP em **cofre/KMS** (ops — já gitignored, ver ADR-065/077).

## Conformidade
CI verde exige `tests/test_email_delivery.py`: o padrão é `InlineDelivery` (e `EMAIL_DELIVERY=
background` seleciona `BackgroundDelivery`); inline entrega já e conta `sent`; background entrega
após drenar o pool; falha do provedor **não propaga** e conta `failed` (inline e background); a
métrica exposta **não** contém corpo/código/destinatário; trocar a entrega **drena** o pool
anterior. `test_notifications.py` (D1) segue **verde sem mudança** (caminho inline). Sem segredo
versionado; o código OTP nunca em log nem em métrica (inegociável #6).
