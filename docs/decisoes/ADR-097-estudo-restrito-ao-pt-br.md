# ADR-097 — O piloto roda só em pt-BR (o app deixa de oferecer inglês)

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) — decisão explícita — + arquiteto (Claude)
- **Etapas relacionadas:** 3 (UX/i18n) e ética/consentimento
- **Contexto de origem:** item **F4.8** do `docs/ROADMAP.md` ("exibir o texto integral também em
  inglês, **ou** restringir o estudo ao pt-BR") e a nota **§N4.6** do `docs/tcle-rascunho.md`.
- **Relaciona-se com:** ADR-070 (i18n pt/en), ADR-071/TCLE integral no app, ADR-089 (consentimento).

## Contexto

O app nasceu bilíngue (ADR-070): a interface responde ao idioma do aparelho em pt-BR ou inglês.
O **TCLE**, porém, existe só em português — é o documento que vai ao CEP e o que vincula o
participante. O resumo de 7 tópicos na tela de consentimento **está** traduzido; o texto integral,
não.

Isso produz um cenário ruim e silencioso: alguém com o celular em inglês lê um resumo em inglês,
toca em "Agree and continue" e o que fica registrado é o aceite de um documento que essa pessoa não
teve como ler. Resumo não é consentimento informado — é justamente por isso que o texto integral
foi levado para dentro do app. A tela já avisava, em inglês, que "o termo oficial está em
português", mas um aviso não resolve: ou existe versão em inglês do termo, ou o estudo não admite
quem depende dela.

Traduzir o TCLE tem custo que não é de tradução: seria **outro documento a submeter, aprovar e
versionar** junto ao CEP, e a divergir do português a cada revisão. Para um piloto de N≈40 numa
instituição brasileira, é trabalho sem participante do outro lado.

## Decisão

1. **O estudo é em pt-BR.** O mantenedor optou por restringir, e não por traduzir o termo.
2. **`AppLocalizations.supportedLocales` passa a ser só `[pt]`.** O `WidgetsApp` resolve o locale
   do aparelho contra essa lista, então **qualquer** idioma cai em pt-BR — inclusive a tela da
   equipe (ADR-096). Ninguém consente por uma interface cujo documento correspondente não existe.
3. **A tradução `en` continua no código**, agora sob `translatedLocales`. Não é código morto por
   descuido: é a máquina de i18n do ADR-070 preservada e testada. Reabrir o inglês é devolver
   `Locale('en')` a `supportedLocales` — **junto com um TCLE em inglês**, que é o que de fato falta.
4. **O delegate recusa `en`** (`isSupported` olha `supportedLocales`, não `translatedLocales`) —
   existir tradução não é o mesmo que o estudo aceitar aquele idioma. Há teste guardando isso.
5. **Critério de elegibilidade:** "**compreender português**" entra no §4 do TCLE. A redação final
   é do protocolo/CEP; o que esta decisão fixa é que o critério **precisa existir**, porque sem ele
   o estudo admitiria alguém de quem não se pode obter consentimento informado.
6. **O aviso "o termo oficial está em português" fica no código**, hoje inalcançável. Se `en` voltar
   a `supportedLocales` sem que alguém revisite este ADR, o aviso reaparece sozinho — melhor uma
   rede de segurança inerte do que a ausência dela no dia em que voltasse a ser necessária.
7. **Os testes de tela passam a provar a restrição** ("aparelho em inglês continua vendo pt-BR") em
   vez da troca de idioma; a cobertura do inglês migra para a camada de strings.

## Alternativas consideradas

- **Traduzir o TCLE integral para inglês** (a outra metade do F4.8). Rejeitada pelo mantenedor:
  cria um segundo documento a submeter, aprovar e manter sincronizado com o português a cada
  revisão do CEP — para um piloto local, sem participante que precise dele.
- **Manter a interface bilíngue e só avisar que o termo é em português.** Rejeitada: é o estado
  atual, e é exatamente o que o F4.8 aponta como problema. O aviso transfere ao participante um
  risco que é do desenho do estudo.
- **Apagar as strings `en`.** Rejeitada: destruiria a prova de internacionalização do ADR-070 e
  transformaria "reabrir o inglês" de uma linha em um retrabalho. Elas ficam, não oferecidas.
- **Traduzir só o resumo e manter o integral em português** (o estado de hoje, formalizado).
  Rejeitada: é o pior dos dois mundos — dá a impressão de que a pessoa pode participar em inglês.
- **Restringir por país/loja em vez de por idioma.** Rejeitada: não é a mesma coisa; há quem viva
  no Brasil e use o aparelho em inglês, e é exatamente essa pessoa que o `supportedLocales` protege.

## Consequências

**Positivas:** desaparece a possibilidade de consentir por uma interface sem documento
correspondente; o critério de elegibilidade passa a refletir a realidade do material; a i18n
continua viva para depois do piloto. Suíte: **49 testes de widget** (os que exercitavam o inglês
foram reescritos, não removidos).

**Negativas / a vigiar:**
- **O app fica monolíngue de fato**, ainda que bilíngue no código. Quem olhar só a tela pode
  concluir que a i18n foi abandonada — daí a distinção explícita entre `supportedLocales` e
  `translatedLocales`.
- **A tradução `en` vai envelhecer.** Nenhum teste de tela a exercita mais; se uma string nova
  entrar só em pt, o fallback cobre e ninguém percebe. Ao reabrir o inglês, revisar tudo.
- **O critério de língua ainda não é aplicado pelo sistema.** A triagem (`screening`) não pergunta
  idioma, e nem deveria antes de o protocolo definir a redação — hoje isso é procedimento de
  recrutamento, não código.
- Um `!` de destaque no TCLE é dirigido ao **participante**: a justificativa desta decisão ficou nas
  notas (§N4.6), não no corpo do termo. O gerador do asset converte citação em destaque, então uma
  nota editorial dentro do termo apareceria na tela de consentimento.

## Verificação

`app/test/i18n_a11y_test.dart`: aparelho em inglês continua vendo pt-BR na Home, no login, no
consentimento (inclusive o acesso ao termo integral), no pós-sessão e nos títulos de B2–B6; o
delegate **recusa** `en` e aceita `pt`; `supportedLocales == [pt]` enquanto `translatedLocales`
mantém `en`, com as strings inglesas ainda íntegras (`startSession`, `consentTitle`,
`tcleFullTitle`, GAD-7, SUS). `app/test/tcle_full_text_test.dart`: com o aparelho em inglês, a tela
do termo abre em pt-BR e mantém o aviso de RASCUNHO. `app/test/staff_setup_test.dart`: a tela da
equipe também. `scripts/sync_tcle.py --check` (job `contracts`) garante que o §4 alterado está no
asset empacotado.
