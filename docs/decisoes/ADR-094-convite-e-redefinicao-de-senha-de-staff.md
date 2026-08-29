# ADR-094 — Convite e redefinição de senha de staff por token de uso único

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** item **F4.7** do `docs/ROADMAP.md` ("reset de senha por admin + convite por
  e-mail (staff)"), item **C3** do checklist, autorizado pelo mantenedor.
- **Relaciona-se com:** ADR-081 (lifecycle de staff), ADR-063 (OTP — mesmo padrão de segredo),
  ADR-074 (MFA obrigatório), ADR-091 (expurgo de transitórios), ADR-085/092 (entrega de e-mail).

## Contexto

O ADR-081 fechou o *lifecycle* de staff (criar, listar, ativar/desativar, rotacionar a própria
senha), mas deixou dois buracos operacionais que só apareceriam no pior momento — durante a coleta:

- **Criar staff exigia o admin escolher a senha** e transmiti-la por fora (WhatsApp, papel, voz).
  Além de frágil, isso significa que **o admin conhece a senha do pesquisador**: com ela e sem MFA
  cadastrado ainda, o admin pode agir como outra pessoa, e a trilha de auditoria — que atribui a
  ação ao dono da conta — passa a mentir sobre a autoria.
- **Não havia recuperação.** Um pesquisador que esquecesse a senha dependia de alguém editar o banco
  à mão, no meio de um estudo em andamento.

## Decisão

1. **Um mecanismo só para os dois casos: o staff define a própria senha** a partir de um **token de
   uso único** enviado ao seu e-mail. `purpose` (`invite` | `reset`) muda só o texto e a auditoria.
2. **`POST /v1/staff` com `password` opcional.** Sem senha no corpo → **convite**: a conta nasce com
   hash de uma senha aleatória **desconhecida por todos** (`unusable_password_hash()`), e o link vai
   para a pessoa. A resposta traz `invited: true`. Com senha, o comportamento antigo é preservado.
3. **`POST /v1/staff/{id}/password-reset` (admin `user:manage`)** dispara o link **para o e-mail do
   próprio staff**. O admin **não escolhe a senha e não vê o token** — destrava um colega sem ganhar
   um caminho para assumir a conta dele. A resposta devolve só `status` e `expires_at`.
4. **`POST /v1/staff/setup-password` (público)** consome o token e grava a senha. Público porque
   quem o usa, por definição, **não consegue autenticar**. Protegido por rate limit por IP
   (`staff_setup`, 10/min) e resposta genérica.
5. **Segredo tratado como o OTP (ADR-063):** 32 bytes aleatórios (`token_urlsafe`), gravados **só
   como `sha256(token+pepper)`** com pepper próprio (`STAFF_SETUP_PEPPER`); uso único; expiração;
   emitir um novo **invalida os pendentes** da pessoa. Quem lê o banco não consegue usar o link.
6. **TTLs distintos por intenção:** convite **72 h** (a pessoa precisa achar tempo), redefinição
   **2 h** (é reação a um problema em curso — a janela deve fechar rápido). Ambos por ambiente.
7. **Definir senha NÃO mexe no MFA.** Invariante explícita e testada: quem tinha segundo fator
   continua precisando dele. Caso contrário, "resetar a senha" viraria o atalho de um admin para
   contornar o MFA de um pesquisador — justamente o caminho de insider que o ADR-074 fecha.
8. **Conta desativada não recebe link (409) nem consome um emitido antes (401).** Suspensão tem de
   ser suspensão; reative deliberadamente antes.
9. **Resposta genérica 401** para token inexistente, expirado, consumido ou de conta desativada — os
   quatro indistinguíveis de fora, para o endpoint público não virar oráculo.
10. **Auditoria sem segredo e sem PII:** `staff.invited`, `staff.password_reset_requested`,
    `staff.password_set` — com quem, sobre quem e o `purpose`. Nunca o token, a senha ou o e-mail.
11. **Retenção desde o primeiro dia:** `purge_expired_staff_tokens()` entra no módulo `retention` e
    no job já agendável (`scripts/purge_otp.py`), com o mesmo critério absoluto do ADR-091. Uma
    tabela nova de credencial transitória sem expurgo seria exatamente o acúmulo que o R-10 cobra.
12. **Contrato antes do código** (`shared-contracts/openapi.yaml`) e **uma migração**
    (`e5f6a7b8c9d0`), com índice em `token_hash` — o consumo busca por hash num endpoint público.

## Alternativas consideradas

- **Admin define a senha nova e informa à pessoa.** Rejeitada: é o problema, não a solução — o admin
  passa a conhecer a credencial de outra pessoa e a autoria da auditoria deixa de ser confiável.
- **Devolver o token na resposta da API** (para o admin repassar). Rejeitada pelo mesmo motivo: o
  token é equivalente à senha durante a janela. Ele existe em claro **só** no e-mail do dono.
- **Reusar `otp_challenge`.** Rejeitada: são vidas e semânticas diferentes (5 min × 72 h,
  participante × staff, 6 dígitos × 32 bytes) e a coabitação embaralharia o expurgo e a auditoria.
- **Link de "esqueci minha senha" self-service** (a própria pessoa pede sem admin). Rejeitada por
  ora: cria um endpoint público que dispara e-mail a partir de um endereço fornecido — enumeração e
  abuso de envio para um time de 2 a 5 pessoas em que pedir ao admin é trivial.
- **Desativar o MFA junto com a redefinição** ("a pessoa perdeu o celular também"). Rejeitada: seria
  o atalho descrito na decisão 7. O caminho para MFA perdido continua sendo a decisão explícita de
  um admin sobre a conta, com registro.

## Consequências

**Positivas:** ninguém além do dono conhece a senha de uma conta de staff; existe caminho de
recuperação sem editar banco; o MFA não é contornável por reset; a nova credencial transitória já
nasce com expurgo e auditoria. **+14 testes** (suíte 328→342).

**Negativas / a vigiar:**
- **Não há página de "definir senha" no app.** O cliente Flutter é do participante; o staff usa a
  API direto. Sem `STAFF_SETUP_URL` configurada, o e-mail carrega o token cru e a pessoa precisa
  chamar `POST /v1/staff/setup-password` na mão. **Enquanto não houver painel de staff, este é o
  procedimento** — está declarado, não escondido.
- **Depende de e-mail funcionando** (F3.2). Sem SMTP real, o convite não chega: em dev o token sai
  no console, o que é aceitável só em dev.
- O token no corpo do e-mail herda a exposição do canal e-mail — mitigado por TTL curto, uso único e
  invalidação do anterior, mas é a mesma superfície do OTP, já aceita no RIPD.
- Um admin ainda pode **desativar** uma conta e **criar** outra: a separação de papéis do piloto é
  pequena por desenho. A auditoria registra ambos os atos.

## Verificação

`tests/test_staff_onboarding.py` (14): criar sem senha convida e manda o link **para a pessoa**;
conta convidada não aceita senha vazia, a do admin, nem "password"; o link define a senha e permite
login; **uso único** (2º uso = 401 idêntico ao de token inexistente); reset por admin não revela o
token; **redefinir não desliga o MFA** (resposta e banco); token novo invalida o pendente; conta
desativada não recebe (409) nem consome (401); 404 para staff inexistente e 403 para researcher;
token expirado não serve; auditoria sem token, senha ou e-mail; rate limit (429) no endpoint
público; expurgo alcança os expirados e é idempotente; token guardado **só como hash**.
