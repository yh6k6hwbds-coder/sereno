# ADR-047 — Autenticação de participante por e-mail + OTP (sem senha)

- **Status:** Aceito
- **Data:** 2026-07-03
- **Etapas relacionadas:** 5 (segurança)
- **Contexto de origem:** 7ª fatia (acesso do participante)

## Contexto
Participantes de pesquisa (possivelmente vulneráveis) não deveriam gerir senha: é fricção e
risco (reuso, vazamento). Precisamos de um acesso simples, seguro e sem enumeração.

## Decisão
1. **E-mail + código de uso único (OTP)**: o participante informa o `study_code`, recebe um
   OTP de 6 dígitos e, ao verificá-lo, recebe um JWT de participante (papel `participant`).
2. **Nova tabela `otp_challenge`** (migração incremental): guarda apenas o **hash** do código
   (`sha256(código+pepper)`), `expires_at`, `consumed`, `attempts`.
3. **Defesas**: expiração curta (5 min), **uso único**, **limite de tentativas** (a tentativa
   é persistida mesmo em erro — resiste a brute force), e **sem enumeração** (solicitar OTP
   responde de forma genérica; falhas de verificação retornam 401 genérico).
4. **Entrega por e-mail** ao contato cifrado é **integração à parte** (PROD/SMTP); em DEV é
   abstraída por `deliver_otp` (o código nunca é logado em produção).

## Alternativas consideradas
- **Senha + argon2 (como staff).** Rejeitada para participante: fricção/risco desnecessários.
- **Magic link.** Equivalente ao OTP; adiada (OTP é mais simples de testar e usar offline-first).
- **Guardar o OTP em claro.** Rejeitada: só o hash é persistido.

## Consequências
- **Positivas:** acesso simples e seguro; PII (e-mail) permanece cifrada/separada; testado
  (uso único, expiração, tentativa, sem enumeração).
- **Custo/tradeoff:** OTP de 6 dígitos é de baixa entropia — mitigado por expiração+limite+uso
  único+pepper. Entrega por e-mail é dependência externa ainda pendente.
- **Pendências:** wiring de SMTP; custódia do `OTP_PEPPER`; opção de rate limit por IP no request.

## Conformidade
CI exige a suíte de auth de participante passando (verificação, uso único, expiração, tentativa, sem enumeração).
