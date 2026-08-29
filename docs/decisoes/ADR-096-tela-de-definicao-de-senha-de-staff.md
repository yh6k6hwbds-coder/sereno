# ADR-096 — Tela de definição de senha de staff no app web (ponta que faltava do ADR-094)

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 3 (UX) e 5 (backend/segurança)
- **Contexto de origem:** consequência negativa declarada no **ADR-094** ("não há página de definir
  senha; enquanto não houver painel de staff, o convite manda o token cru") e item **F3.10** do
  `docs/ROADMAP.md`.
- **Relaciona-se com:** ADR-094 (convite/redefinição por token), ADR-070 (i18n), ADR-072 (`?api=`
  como override por link na web), ADR-050 (sem router — injeção simples).

## Contexto

O ADR-094 entregou o fluxo inteiro no servidor, mas o link do e-mail não tinha destino: sem
`STAFF_SETUP_URL`, o convite mandava o token em texto e a pessoa precisava montar um `POST` na mão.
Para um estudo cuja equipe não é de programadores, isso não é um fluxo — é um bilhete com uma
instrução impossível. O item ficou registrado como pendência exatamente para não ser esquecido.

A dúvida real era **onde** essa tela mora. Um painel de staff é expansão de escopo explícita
(`CLAUDE.md`), e não é isso que se está construindo aqui: o que falta é **uma** tela, sem sessão,
sem navegação e sem dado de pesquisa.

## Decisão

1. **A tela mora no app web do participante**, alcançável **só** por `?token=` na URL — o mesmo
   idioma do `?api=` (ADR-072), que já é como o app aceita configuração por link na web.
2. **Rota antes do `AuthGate`.** Havendo token, o app abre `SetupPasswordScreen` e **não** o login
   do participante: quem chega por esse link não é participante, e não deve cair na Home de uma
   sessão que porventura esteja guardada naquele navegador.
3. **No mobile a tela não existe.** `Uri.base` não traz query no APK, então o getter devolve `null`
   e o app abre normalmente. Sem rota, sem *deep link*, sem superfície nova no aplicativo nativo.
4. **A tela não autentica e não guarda nada.** Define a senha e para. Diz, no sucesso, que a conta
   é usada na API de pesquisa e que **não há painel da equipe aqui** — melhor uma frase honesta que
   um botão "entrar" que não leva a lugar nenhum.
5. **Validação local antes de chamar** (mínimo de 8 e confirmação igual): erro de digitação não
   pode **gastar o token de uso único** nem uma tentativa do rate limit do endpoint público.
6. **O token sai da barra de endereço** assim que a tela abre (só na web). O token equivale à
   senha durante sua janela: deixá-lo na URL o expõe ao histórico do navegador e ao `Referer` de
   qualquer requisição da página. Isso **não invalida** o token — quem o queima é o consumo no
   servidor —, só encurta o rastro.

   > **Correção de 2026-08-29 (mesmo dia).** A primeira implementação usava
   > `SystemNavigator.routeInformationUpdated` e **não funcionava**: com a estratégia de URL
   > padrão do Flutter web (hash), aquela chamada escreve a rota no **fragmento**. O teste
   > ponta a ponta no navegador mostrou `?…&token=abc#/sereno/?…` — token intacto e um `#` a
   > mais. A limpeza agora é `history.replaceState` via import condicional
   > (`core/url_scrub.dart`; no-op fora da web). **Nenhum teste pegaria isso**: `kIsWeb` é
   > falso no `flutter test`, então o caminho web nunca roda na suíte.
7. **A tela repete que o MFA não muda** (antes e depois de enviar). É a invariante do ADR-094; se a
   pessoa concluir que "redefinir a senha" reiniciou o segundo fator, ela vai tentar entrar sem ele
   e achar que a conta quebrou.
8. **Correção no backend:** o link passou a respeitar query já existente (`&` em vez de um segundo
   `?`). Com `STAFF_SETUP_URL` apontando para o app publicado — que na demo carrega `?api=<túnel>/v1`
   — a concatenação anterior produziria uma URL quebrada.
9. **pt-BR e en**, como o resto do app (ADR-070).

## Alternativas consideradas

- **Painel de staff separado** (outro app/rota administrativa). Rejeitada: é expansão de escopo
  travada no `CLAUDE.md`, e resolveria com um projeto inteiro o que uma tela resolve.
- **Página HTML estática à parte**, servida junto do Pages. Rejeitada: duplicaria tema, i18n e
  tratamento de problem+json fora do app, e criaria um segundo lugar para manter.
- **Deixar como estava** (token cru no e-mail). Rejeitada: transfere para a equipe do estudo um
  trabalho de linha de comando, no pior momento possível — quando alguém perdeu o acesso.
- **Manter o token na URL.** Rejeitada: histórico e `Referer` são vazamentos gratuitos, e limpar
  custa três linhas.
- **Fazer login automático depois de definir a senha.** Rejeitada: o app é do participante; não há
  sessão de staff para abrir aqui, e criar uma seria justamente a expansão de escopo recusada.

## Consequências

**Positivas:** o fluxo do ADR-094 fica utilizável por quem não é técnico; o `STAFF_SETUP_URL` passa
a ter um destino real (a raiz do app publicado); o token deixa de ficar na barra de endereço.
**+7 testes de widget** (42 → 49).

**Negativas / a vigiar:**
- **Uma tela de staff vive no app do participante.** É inalcançável sem token, mas está no mesmo
  *bundle*. Se um dia houver painel próprio, esta tela deve migrar para lá.
- **Depende de `STAFF_SETUP_URL` apontar para a versão publicada** do app. Apontar para um build
  antigo (sem esta tela) faz o link abrir o login do participante — sintoma confuso. Ficou
  registrado no `.env.example`.
- **A limpeza da URL não é coberta por teste automatizado.** `kIsWeb` é falso no `flutter test`, e
  o caminho web só existe no build de verdade — foi assim que a primeira versão quebrada passou no
  CI. A verificação é manual, no navegador, ao mexer nessa área.
- `url_scrub_web.dart` usa `dart:html` (legado) para não acrescentar dependência ao `pubspec` por
  duas linhas. O build web deste projeto é JS; **migrar para `package:web` é pré-requisito se o
  alvo virar wasm**.
- Se o app adotar `go_router` (ADR-050), a limpeza da URL precisa ser reavaliada junto.
- O app publicado passa a **poder** falar com o endpoint de staff. Não é privilégio novo (o endpoint
  é público e limitado por IP por desenho), mas é superfície que antes só existia via API.

## Verificação

`app/test/staff_setup_test.dart` (7): define a senha e mostra o sucesso, enviando token e senha no
corpo; conta com MFA avisa que o segundo fator continua valendo; **senha curta e confirmação
divergente nem chegam a chamar a API**; link inválido mostra o erro do servidor e mantém o
formulário para nova tentativa; falha de conexão não deixa a tela travada carregando; a tela existe
em inglês; a senha começa oculta e o olho revela. No backend, `test_staff_onboarding.py` ganhou o
caso do link com query preexistente (`&token=`, um único `?`) — 15 testes no arquivo.
