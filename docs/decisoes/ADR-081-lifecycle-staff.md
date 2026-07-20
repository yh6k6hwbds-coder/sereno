# ADR-081 — Lifecycle de staff: desativar/reativar, listar e rotação de senha

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança), Etapa 6 (RBAC no servidor)
- **Contexto de origem:** operação do piloto — um pesquisador/admin deixa a equipe (fim de bolsa,
  troca de função) e o acesso dele precisa ser cortado **sem** apagar a autoria das ações passadas.
- **Relaciona-se com:** ADR-043/058 (gestão de staff + MFA), ADR-064 (denylist de `jti`),
  ADR-074 (MFA obrigatório), ADR-066 (LGPD/retenção — o mesmo princípio de suspender ≠ apagar)

## Contexto
Até aqui um `StaffUser` era criado (ADR-058) e cadastrava MFA (ADR-074), mas **não havia como
suspendê-lo**. Removê-lo do banco quebraria a trilha de autoria da auditoria append-only
(decisão inegociável #6: quem fez cada ação de desbloqueio, exportação, gestão). E o RBAC decidia
só a partir do papel no **JWT** — um token válido em mãos continuaria valendo até expirar, mesmo
que a pessoa tivesse saído da equipe. Faltavam também dois utilitários operacionais óbvios:
listar o time (com estado) e trocar a própria senha.

## Decisão
1. **Coluna `staff_user.is_active`** (bool, `server_default=true`; migração `c3d4e5f6a7b8`).
   Desativar **suspende** o acesso e **preserva** o registro (autoria intacta). Ninguém é
   desativado pela migração.
2. **O RBAC confere `is_active` no banco a cada requisição** — `assert_staff_active()` em
   `core/security.py`, chamado dentro de `require(perm)`. Sem isso, desativar só teria efeito
   quando o token expirasse; com isso, o **token já emitido para de valer imediatamente**. Só se
   aplica a papéis de staff; participante tem o seu próprio caminho.
3. **`is_active` também nas fronteiras de emissão de token**, não só no consumo: `POST /auth/token`
   (login), `POST /auth/mfa/verify` (2º fator) e `POST /auth/refresh` recusam staff suspenso. Um
   desafio de MFA emitido **antes** da suspensão não pode ser trocado por tokens plenos depois dela;
   o refresh não pode ressuscitar a sessão.
4. **Endpoints (admin, `user:manage`):**
   - `GET /v1/staff` — lista papel, MFA, ativo, último login. **Nunca** senha nem segredo de MFA.
   - `POST /v1/staff/{id}/deactivate` e `/activate` — 404 inexistente, 409 estado inalterado.
     Um admin **não desativa a si mesmo** (409): evita o lockout de fechar o próprio caminho de volta.
   - Ambos **auditados sem PII**: só ator, alvo, papel e novo estado — o e-mail não entra no log.
5. **`POST /v1/staff/me/password`** — rotação da própria senha. **Exige a senha atual** (posse do
   token não basta), recusa senha nova igual à atual (422) e **revoga o token de acesso usado na
   chamada** (denylist por `jti`, ADR-064): trocar a senha encerra a sessão em curso. Auditado
   sem o segredo (nem a senha, nem o hash).
6. **Mensagem de login genérica** para conta suspensa (`"E-mail ou senha incorretos"`, 401): não
   confirma a existência da conta a quem tenta entrar. O caminho autenticado (RBAC) pode ser
   explícito (`"Acesso suspenso"`), pois lá a identidade já foi provada.

## Alternativas consideradas
- **Apagar a linha do `StaffUser`.** Rejeitada: quebra a autoria da auditoria append-only
  (inegociável #6) — o mesmo motivo pelo qual o `erase` de LGPD (ADR-066) preserva a auditoria.
- **Confiar só no papel do JWT + esperar expirar.** Rejeitada: deixa uma janela (até a expiração
  do access/refresh) em que quem saiu ainda entra. A conferência no banco fecha a janela sem
  precisar encurtar o TTL de todo mundo.
- **Revogar todos os `jti` do staff ao desativar.** Rejeitada por ora: exigiria indexar tokens
  por usuário na denylist; a conferência de `is_active` no RBAC cobre o caso com menos estado.
- **Reset de senha por admin.** Rejeitada no MVP: sem SMTP de fluxo de recuperação (ainda), a
  rotação pelo próprio staff (com a senha atual) cobre a necessidade do piloto; reset por admin
  vira pendência.

## Consequências
- **Positivas:** offboarding real (corta acesso já emitido), listagem operacional do time e troca
  de senha — os utilitários que o piloto vai precisar. Autoria preservada. Suíte 213 → 224 (+11).
- **Custo/tradeoff:** o RBAC passa a fazer **um `SELECT` por requisição** de staff (antes decidia
  só pelo JWT). Custo baixo (get por PK) e restrito a papéis de staff; participante não paga.
- **Pendências:** reset de senha por admin (depende do fluxo de e-mail); expiração/rotação
  programada de credenciais; "último login" (`last_login_at`) já existe na coluna mas o registro
  no login é item à parte.

## Conformidade
CI verde exige `tests/test_staff_lifecycle.py`: admin lista sem expor senha/segredo; desativar
suspende o **token já emitido** (mesmo token: 200 antes, 401 depois) e fecha login/refresh;
reativar restaura; admin não se desativa (409); estado inalterado 409; inexistente 404; auditoria
sem PII; rotação exige senha atual (401 se errada), recusa senha igual (422) e revoga o token
usado; staff suspenso não troca senha (401). `test_recommender_loop.py` atualizado: relatórios de
staff agora usam pesquisador **real** no banco (token com `sub` inexistente é 401, por desenho).
Sem segredo versionado; sem PII/braço em log; decisões inegociáveis preservadas.
