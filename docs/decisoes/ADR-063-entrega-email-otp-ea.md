# ADR-063 — Entrega real de e-mail: OTP do participante + alerta de evento adverso

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Fatia D1 do ROADMAP (SMTP)
- **Relaciona-se com:** ADR-047 (OTP), ADR-059 (cifra de PII), ADR-051 (evento adverso), ADR-031 (fila assíncrona)

## Contexto
Os ganchos `deliver_otp` (login por OTP) e `notify_team` (evento adverso) apenas imprimiam.
D1 os substitui por **envio real de e-mail**, atrás de uma interface (trocar de provedor sem
tocar nas rotas). A entrega do OTP depende da **PII cifrada de C4**: o e-mail do participante é
decifrado só no momento do envio.

## Decisão
1. **Interface `EmailSender`** (`core/email.py`) com implementações escolhidas por ambiente:
   `SmtpEmailSender` (produção; retries + backoff), `NullEmailSender` (não configurado — **padrão
   seguro**, não envia e **não loga o código**), `ConsoleEmailSender` (dev, opt-in via
   `EMAIL_DEV_CONSOLE`), `MemoryEmailSender` (testes).
2. **OTP por e-mail:** `request-otp` resolve o destinatário decifrando `contact_info.enc_email`
   (C4) e envia **best-effort**. O código **nunca é logado**; se não houver contato/chave ou o
   envio falhar, apenas não envia — o código já está gravado e a resposta ao cliente é genérica
   (sem enumeração). A verificação (`verify-otp`) segue igual.
3. **Alerta de EA:** `notify_team` envia para `TEAM_NOTIFY_EMAIL` em gravidade moderate/severe,
   **sem PII** (só id do evento + gravidade). Sem o endereço configurado, não notifica.
4. **Sync best-effort com retries** agora; a **fila assíncrona** (RQ/Redis, ADR-031) é o caminho
   de produção para desacoplar latência/falha — trocável atrás da porta.
5. **Sem mudança de contrato:** os endpoints não mudam de forma; só o comportamento interno de
   envio.

## Alternativas consideradas
- **Fila assíncrona (RQ) já nesta fatia.** Adiada: exige worker/Redis, fora do CI-espelho
  (SQLite); a porta permite plugar depois sem reescrever as rotas.
- **SDK de terceiros (SendGrid/SES).** Evitada: `smtplib` da stdlib + interface mantêm o código
  independente de provedor e sem nova dependência; troca-se a implementação quando escolhermos o
  provedor.
- **Imprimir o código no console por padrão (como antes).** Rejeitada: vazaria o OTP em qualquer
  ambiente mal configurado. Padrão passa a ser `Null` (não envia); console é **opt-in** de dev.
- **Enviar de forma bloqueante e falhar o request em erro de SMTP.** Rejeitada: o OTP já foi
  gravado; derrubar o request por falha de e-mail piora a experiência e vaza estado. Best-effort.

## Consequências
- **Positivas:** OTP chega ao participante por e-mail (fluxo real de login sem senha); equipe é
  alertada em EA relevante; nenhum código em log; sem PII no alerta. Suíte: 93 → 98 testes.
- **Custo/tradeoff (visão do analista):**
  - **Envio síncrono** acopla a latência do `request-otp` ao SMTP; aceitável no piloto (volume
    baixo, uma sessão por vez), mas produção deve migrar para a fila assíncrona (ADR-031).
  - **Dependência operacional:** só há e-mail de OTP se o participante tiver **contato capturado
    (C4)** e a chave de PII estiver configurada; sem isso, o participante não recebe o código.
    Fluxo de inscrição precisa capturar o contato antes do 1º login.
  - **Sem tratamento de bounce/deliverability**; retries são ingênuos (backoff fixo).
  - `ConsoleEmailSender` imprime o código — **dev apenas**, nunca habilitar em produção.
- **Pendências:** fila assíncrona (RQ) + idempotência de envio; segredo SMTP em cofre; tratamento
  de bounces; rate limit de envio (além do de request, já em D2).

## Conformidade
CI verde exige `tests/test_notifications.py`: `request-otp` **envia o código por e-mail** (com
contato cifrado) e a verificação com esse código emite token; **sem contato, nada é enviado** (e
a resposta segue genérica); EA **severe** notifica a equipe (sem PII) e **mild** não; sem
configuração de e-mail o padrão é `NullEmailSender` (não envia, não vaza o código).
