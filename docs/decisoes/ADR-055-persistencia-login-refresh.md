# ADR-055 — Persistência de login + refresh transparente (cliente)

- **Status:** Aceito (código completo; validação via CI `app` — ver Conformidade)
- **Data:** 2026-07-05
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 3 (UX/cliente), 5 (auth)
- **Contexto de origem:** Fatia B1 do ROADMAP
- **Relaciona-se com:** ADR-047 (OTP), ADR-064 (refresh/denylist), ADR-050 (fundação Flutter)

## Contexto
O app já guardava os tokens (armazenamento seguro) após o OTP, mas sempre abria no login e não
renovava o acesso ao expirar. B1 adiciona **auto-login**, **refresh transparente no 401** e
**logout**.

## Decisão
1. **Auto-login:** `AuthGate` decide a tela inicial pela sessão persistida
   (`store.isAuthenticated()`): abre a **Home** se houver token, senão o **OTP**.
2. **Refresh no 401 (transparente):** no `ApiClient`, uma chamada autenticada que recebe **401**
   dispara `POST /auth/refresh` com o refresh token; em sucesso, salva os novos tokens e **repete
   a chamada uma vez**. Se o refresh falhar (ou não houver refresh token), **encerra a sessão**
   (limpa o armazenamento seguro) e propaga o erro.
3. **Logout:** ação na Home limpa o armazenamento e volta ao OTP.
4. **Escopo deliberado — SEM Riverpod/go_router agora:** o ROADMAP sugeria adotar Riverpod +
   go_router nesta fatia. Optou-se por **manter a injeção simples por construtor** e entregar o
   valor de B1 (persistência/refresh/logout) com **mudança mínima e testável**, adiando o refactor
   de estado/roteamento (ver Alternativas).

## Alternativas consideradas
- **Refactor para Riverpod + go_router nesta fatia.** Adiado: é um refactor amplo e, sem SDK
  Flutter no ambiente de dev (não dá para compilar/rodar localmente) e com o **job de CI Flutter
  agora bloqueante** (D5), reescrever roteamento/estado às cegas é arriscado. A injeção por
  construtor atual já isola a lógica (testável com fakes); migrar depois, numa fatia dedicada.
- **Refresh via interceptor de uma lib HTTP (dio).** Rejeitada: manteríamos `http` (já usado) e a
  lógica de refresh cabe em poucas linhas testáveis, sem nova dependência.
- **Renovar proativamente antes de expirar (timer).** Rejeitada por ora: reagir ao 401 é mais
  simples e suficiente; renovação proativa é otimização futura.

## Consequências
- **Positivas:** sessão persiste entre aberturas; expiração do access é transparente ao usuário;
  logout limpa o estado. Lógica de refresh coberta por testes com `MockClient` + store fake.
- **Custo/tradeoff (visão do analista):**
  - **Retry único:** evita laço infinito; se o segundo 401 vier, o erro sobe (correto).
  - **`AuthGate` só decide na abertura:** se o refresh falhar **no meio** de um fluxo, a sessão é
    limpa mas a tela atual não redireciona sozinha — o próximo gate/relogin trata. Redirecionar
    reativo ao logout (ex.: um `authState` observável) é a evolução com Riverpod.
  - **Débito técnico consciente:** sem Riverpod/go_router, telas ainda constroem repositórios
    inline; aceitável no piloto, a refatorar antes de crescer (B2–B6).
- **Pendências:** Riverpod + go_router (fatia dedicada); redirecionamento reativo ao logout;
  renovação proativa; empacotar as fontes da identidade (ADR-050).

## Conformidade
Testes em `app/test/auth_flow_test.dart`: 401 dispara refresh e **repete** a chamada (novos tokens
salvos); refresh inválido **encerra a sessão** e propaga o 401; sem refresh token **não** tenta
refrescar; `AuthGate` abre **Home** com sessão e **OTP** sem sessão. **Ressalva:** sem SDK Flutter
na máquina de dev, os testes **não foram rodados localmente** — a validação é o job `app` do CI,
agora **bloqueante** (ADR-067). Código revisado estaticamente.
