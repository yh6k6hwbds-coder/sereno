# ADR-074 — MFA obrigatório para staff (token de cadastro restrito)

- **Status:** Aceito
- **Data:** 2026-07-05
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança)
- **Contexto de origem:** Pendência da fatia C3 ("exigir MFA para admin") — endurecimento para dado real/CEP
- **Relaciona-se com:** ADR-043 (auth staff argon2+JWT+MFA), ADR-058 (gestão de staff + cadastro de MFA), ADR-064 (denylist de `jti`)

## Contexto
O `CLAUDE.md` (decisão inegociável #6) exige **MFA para staff**. Mas o login (ADR-043/058)
só pedia o 2º fator quando `mfa_enabled=True`; um pesquisador/admin que **simplesmente não
cadastrasse** o MFA recebia **acesso pleno só com senha**. Ou seja, o 2º fator era, na prática,
**opcional** — qualquer staff contornava a exigência por omissão. Para coletar dado real (PII de
participantes) e ir ao CEP, isso precisa ser fechado.

Há um ovo-galinha: para cadastrar o MFA (`/staff/me/mfa/enroll` e `/confirm`, ADR-058) é preciso
estar autenticado — mas o acesso pleno é justamente o que não se quer conceder antes do 2º fator.

## Decisão
1. **Login sem MFA ativo não concede acesso pleno.** Se a senha confere mas `mfa_enabled=False`,
   `POST /auth/token` responde `{mfa_enrollment_required: true, enrollment_token: <jwt>}` — **sem**
   `access_token`/`refresh_token`.
2. **Token de "enroll" (tipo próprio, sem escopo).** `auth.issue_enrollment` emite um JWT de
   `type="enroll"`, `scope=""`, TTL curto (`ENROLL_TTL_MIN`, 10 min). Como `current_user` exige
   `type="access"`, esse token **é recusado em todo endpoint protegido** (401) — só serve para
   cadastrar o MFA.
3. **Enroll/confirm aceitam `access` OU `enroll`.** Nova dependência `current_staff_enrolling`
   valida assinatura/exp, aceita apenas esses dois tipos e respeita a denylist de `jti`. Um token
   de acesso pleno também vale (permite **rotacionar** o MFA já autenticado).
4. **Sem migração; sem novo endpoint.** Só muda o desfecho do login e o guard do cadastro. O
   contrato (`TokenResponse`, `/auth/token`) foi atualizado **antes** do código.

Efeito colateral desejável: o **bootstrap do 1º admin** fica seguro — um admin semeado só com
senha (sem MFA) consegue, no primeiro login, **apenas** cadastrar o MFA; nada mais.

## Alternativas consideradas
- **Bloquear o login por completo até haver MFA.** Rejeitada: impossível cadastrar o 2º fator
  sem antes autenticar (o ovo-galinha). O token de graça restrito resolve isso sem abrir acesso.
- **`confirm` já devolver os tokens de acesso.** Adiada: reduz um passo, mas mistura o fluxo de
  cadastro com o de sessão; hoje o staff faz um novo login (agora já com TOTP). Simplicidade > atalho.
- **Exigir MFA só para `admin`.** Rejeitada: `researcher` também vê/expõe dados de pesquisa;
  a decisão inegociável fala em **staff**, não só admin. Uniforme é mais simples e mais seguro.
- **Marcar `mfa_enabled` como NOT NULL default e forçar via schema.** Desnecessário: a imposição
  é no fluxo de emissão de token, não em invariante de linha.

## Consequências
- **Positivas:** o 2º fator deixa de ser evitável; nenhum caminho concede acesso pleno de staff
  sem TOTP; bootstrap do 1º admin fica seguro por construção. Suíte: 147 → 149 testes.
- **Custo/tradeoff (visão do analista):**
  - Tokens de acesso **cunhados diretamente** (fora do login) continuam válidos — é assim que os
    testes montam headers e é legítimo (a imposição é no login/refresh, os únicos caminhos de
    produção para obter um token). Não enfraquece produção.
  - `refresh` não re-checa `mfa_enabled`: um refresh só existe após um login com MFA, então herda a
    garantia; se o MFA for desativado depois, o refresh vale até expirar (aceitável no piloto).
  - A senha inicial ainda é definida pelo admin (pendência de rotação do ADR-058 permanece).
- **Pendências:** rotação/troca de senha; convite por e-mail; lifecycle de staff (listar/desativar);
  política de "desabilitar MFA" (hoje não há endpoint — desativar exige intervenção no banco).

## Conformidade
CI verde exige `tests/test_auth.py`: login sem MFA → `mfa_enrollment_required` + `enrollment_token`
(tipo `enroll`, sem escopo), **sem** access/refresh; o token de `enroll` **não** abre endpoint
protegido (401 ao tentar `POST /staff`); onboarding completo (login → enroll → confirm → login exige
TOTP → acesso). `tests/test_staff.py` (enroll/confirm com token de acesso; participante → 403) e
`tests/test_throttle.py` (senha errada conta o limite) seguem verdes.
