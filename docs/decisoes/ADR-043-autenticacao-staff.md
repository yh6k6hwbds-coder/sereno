# ADR-043 — Autenticação de staff (argon2id + JWT + MFA TOTP)

- **Status:** Aceito
- **Data:** 2026-07-03
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (segurança)
- **Contexto de origem:** 2ª fatia vertical (substituir os stubs de autenticação)

## Contexto
O esqueleto usava `current_user` como stub. Antes de gravar qualquer dado clínico
(PSQI/GAD-7), o controle de acesso precisa ser real — inclusive para a submissão ao CEP.

## Decisão
1. **Login de staff** (`POST /auth/token`): senha verificada com **argon2id**; sem
   enumeração de usuário (falhas retornam 401 genérico "Credenciais inválidas").
2. **MFA obrigatório para quem o habilita**: se `mfa_enabled`, o login devolve um
   **token de desafio** curto (tipo `mfa`, 5 min) — sem acesso — e exige TOTP em
   `POST /auth/mfa/verify` (tolerância de ±30s). Só então emite os tokens.
3. **JWT**: `access` curto (15 min) + `refresh` (7 dias), com `type`, `jti`, `iat`,
   `nbf`, `exp`. `current_user` valida assinatura, expiração e tipo do token.
4. **RBAC** inalterado; o token carrega `role` e `scope` derivado da matriz.
5. **Autenticação de participante** é uma **fatia à parte** (fluxo mais simples,
   p. ex. e-mail/OTP); aqui o participante é derivado do `sub` do token.

## Alternativas consideradas
- **Sessão por cookie/servidor.** Rejeitada: JWT stateless casa melhor com cliente
  móvel e com o contrato REST; revogação fina fica para quando necessário (lista de `jti`).
- **Sem MFA no MVP.** Rejeitada para staff: o acesso a dados de pesquisa exige 2º fator.
- **RS256 já agora.** Adiada: HS256 com segredo em variável de ambiente é suficiente no
  piloto; **produção deve usar segredo forte em cofre, com rotação, e avaliar RS256**.

## Consequências
- **Positivas:** fecha o buraco de segurança dos stubs; endpoints de pesquisa protegidos
  de verdade (cadeia token→RBAC testada); MFA para staff.
- **Custo/tradeoff:** JWT stateless não revoga individualmente antes do `exp` (mitigável
  com denylist de `jti` se/quando necessário). Segredo HS256 precisa de custódia adequada.
- **Pendências:** implementar a fatia de autenticação de participante; gestão de usuários
  de staff (criação por admin — `user:manage`).

## Conformidade
CI verde exige a suíte de auth passando (login, MFA, refresh, RBAC) além das demais.
Em produção: `JWT_SECRET` forte em cofre; nunca versionar segredos.
