# ADR-070 — i18n + acessibilidade (fundação no cliente)

- **Status:** Aceito
- **Data:** 2026-07-09
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 3 (UX/identidade e cliente)
- **Contexto de origem:** Fatia E5 do ROADMAP (Fase E — pós-piloto; escopo liberado pelo mantenedor)
- **Relaciona-se com:** ADR-018/019 (identidade e tema), ADR-020 (visualização NÃO reativa)
  **[inegociável]**, ADR-052 (UI idêntica entre braços) **[inegociável]**

## Contexto
O cliente Flutter tinha todas as strings **hardcoded** em pt-BR e a visualização ambiente
(`BreathingWave`) animava em `repeat()` **incondicional** — sem respeitar a preferência de
"movimento reduzido" do sistema (apesar de o ROADMAP supor que já respeitava). Esta fatia é a
**fundação** de i18n + acessibilidade, começando pela Home e pelos componentes transversais.

## Decisão
1. **i18n por delegate MANUAL** (`lib/l10n/app_localizations.dart`): um `LocalizationsDelegate`
   próprio com mapa de strings por locale (**pt-BR** padrão/fallback, **en** para provar a
   internacionalização). `AppLocalizations.of(context)` é **tolerante**: sem localização na árvore,
   cai no pt-BR (nunca lança) — assim widgets testados isolados seguem funcionando.
2. **Delegates Global** (`flutter_localizations`) ligados no `MaterialApp` para localizar também os
   widgets Material/Cupertino em pt/en.
3. **Acessibilidade:**
   - CTA primário de sessão com **semântica de botão rotulada** (`Semantics(button, label)`).
   - `BreathingWave` respeita **movimento reduzido** (`MediaQuery.disableAnimations`): desliga o
     `repeat()` e mostra um quadro estático — **sem** tornar-se reativa ao áudio (cegamento intacto).

## Alternativas consideradas
- **Pipeline oficial ARB + `intl` + `gen-l10n`.** Deferida: exige um passo de **geração no build**,
  e o ambiente de dev não tem SDK Flutter (validação é o CI) — um delegate manual é mínimo,
  totalmente testável e sem code-gen. Migrar para ARB depois é transparente para as telas (só
  consomem `AppLocalizations.of`).
- **Traduzir todas as telas de uma vez.** Rejeitada: fatia mínima (Home + disclaimer) primeiro;
  as demais telas migram incrementalmente. Simplicidade > big-bang.
- **Ocultar a visualização sob movimento reduzido.** Rejeitada: um quadro estático preserva a
  identidade e a **paridade entre braços** (UI idêntica) melhor que remover o elemento.

## Consequências
- **Positivas:** base de i18n pronta (trocar de idioma é só o `locale`), Home e disclaimer
  bilíngues, e a visualização agora acessível a quem pede menos movimento. Nada quebra o cegamento.
- **Custo/tradeoff (visão do analista):** as **demais telas** (OTP, consentimento, sessão, B2–B6)
  ainda têm strings pt-BR hardcoded — migram em fatias seguintes. O delegate manual não valida
  plurais/gênero/datas como o `intl` faria; se isso virar necessidade, promover para ARB.
- **Pendências:** migrar as telas restantes; extrair para ARB/`intl` se o piloto internacionalizar
  de fato; auditoria de contraste (AA) e navegação por leitor de tela ponta a ponta.

## Conformidade
CI verde (job `app`, bloqueante) exige `test/i18n_a11y_test.dart`: a Home renderiza pt-BR por
padrão e **en** quando `locale=en` (troca real de strings, incluindo o disclaimer); o CTA de sessão
expõe **semântica de botão rotulada**; e a `BreathingWave` sob `disableAnimations` **assenta**
(`pumpAndSettle` não trava) — prova de que o `repeat()` foi desligado. Testes anteriores da Home
seguem verdes pelo fallback pt-BR.
