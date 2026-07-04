# ADR-058 — Gestão de staff + cadastro de MFA (TOTP)

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Fatia C3 do ROADMAP
- **Relaciona-se com:** ADR-043 (auth staff argon2+JWT+MFA), ADR-056 (auditoria)

## Contexto
A `staff_user` existia, mas não havia como **criar** pesquisadores/admins nem **cadastrar MFA**.
Sem isso, o time só existia por seed manual e o 2º fator (previsto no ADR-043) não tinha fluxo de
ativação. Necessário sem abrir auto-registro público (superfície de abuso).

## Decisão
1. **`POST /v1/staff`** (admin `user:manage`): cria pesquisador/admin com senha **argon2id**;
   e-mail **único** (409); papel restrito a `researcher|admin`. **Sem auto-registro público** —
   só admin cria. Auditado (`staff.created`) **sem** e-mail/senha (só o papel).
2. **Cadastro de MFA em dois passos** (evita lockout):
   - `POST /v1/staff/me/mfa/enroll`: gera e guarda o segredo TOTP e devolve o `provisioning_uri`
     (otpauth://) + o `secret` (entrada manual). **Não ativa** o MFA ainda.
   - `POST /v1/staff/me/mfa/confirm`: valida um código TOTP contra o segredo e então **ativa**
     (`mfa_enabled=True`); código errado → 401. Auditado (`mfa.enabled`).
3. **MFA é pessoal e auto-cadastrado:** o endpoint é `me`; ninguém cadastra MFA por outro.
4. **Sem migração:** a tabela e os campos (`mfa_secret`, `mfa_enabled`) já existiam.

## Alternativas consideradas
- **Enroll ativa o MFA imediatamente.** Rejeitada: se o usuário não conseguir gerar códigos
  (relógio/app errado), fica trancado fora. O passo de confirmação prova posse antes de ativar.
- **Admin define/ativa MFA de terceiros.** Rejeitada: o segredo TOTP é pessoal; expô-lo a um
  admin enfraquece o 2º fator. Só auto-cadastro.
- **Convite por e-mail + senha temporária.** Adiada: depende do fluxo de e-mail (D1) e de
  expiração de convite; no piloto, o admin define a senha inicial (a rotacionar).

## Consequências
- **Positivas:** o time é gerido pela API (sem seed manual); o 2º fator tem ativação segura;
  ações sensíveis auditadas sem vazar segredo. Suíte: 111 → 121 testes.
- **Custo/tradeoff (visão do analista):**
  - O `secret` volta na resposta do enroll (para QR/entrada manual) — trafega **só sob TLS** e
    **nunca** é logado/auditado; ainda assim, é um ponto a proteger (evitar cache/registro no cliente).
  - **Senha inicial definida pelo admin:** sem rotação forçada nem política de expiração ainda;
    recomendável forçar troca no 1º login (futuro).
  - **MFA é opcional por usuário:** não há política que o **exija** (ex.: obrigatório para admin).
    Tornar MFA mandatório para papéis sensíveis é decisão de política a registrar depois.
- **Pendências:** exigir MFA para admin; troca de senha/rotação; convite por e-mail; listar/
  desativar staff (lifecycle completo).

## Conformidade
CI verde exige `tests/test_staff.py`: admin cria staff (senha **cifrada**, verificável; sem PII/
senha na resposta ou no log); e-mail duplicado → 409; **não-admin → 403**, sem token → 401;
entradas inválidas → 422; criação **auditada sem e-mail**; enroll devolve `otpauth://` e guarda o
segredo **sem ativar**; confirm com TOTP válido **ativa** e o login passa a exigir o 2º fator;
código errado → 401; participante não cadastra MFA (403).
