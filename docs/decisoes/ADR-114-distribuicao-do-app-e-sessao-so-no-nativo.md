# ADR-114 — Distribuição do aplicativo: Android por link direto, e a sessão só onde a fidelidade vale

- **Status:** Aceito
- **Data:** 2026-09-01
- **Decisores:** Arquiteto (Claude), com ratificação do mantenedor
- **Etapas relacionadas:** 2 (player/instrumento), 3 (UX), 7 (operação do estudo)
- **Contexto de origem:** item **H5** do `docs/ROADMAP.md`; lacuna nº 3 da auditoria operacional
  de 2026-08-29.
- **Relaciona-se com:** decisão inegociável **#3** (reprodução bit-a-bit), ADR-103 (entrega em
  FLAC e cache local cifrado), ADR-105 (critérios de elegibilidade), ADR-096 (o app web hospeda a
  tela de senha da equipe).

## Contexto

Três coisas estavam abertas e eram tratadas como uma só:

1. **Não existe build iOS.** O repositório não guarda pastas nativas; o CI faz
   `flutter create --platforms=android`. Um build iOS exigiria um Mac, uma conta paga de
   desenvolvedor e um ciclo de revisão — nada disso existe no projeto.
2. **O APK sai como *artifact* do GitHub Actions**, baixável só por quem tem acesso ao
   repositório, e **assinado com a chave de debug** — que é pública, que nenhuma loja aceita e
   cuja troca posterior obriga a desinstalar o aplicativo (levando junto o cache cifrado de áudio).
3. **A fidelidade bit-a-bit nunca foi verificada no navegador.** A inegociável #3 foi testada na
   pilha nativa. E o app web está publicado, funcionando, oferecendo o botão "Iniciar sessão".

O terceiro é o que muda a natureza da decisão. Não é uma questão de conveniência de distribuição:
é o **instrumento do estudo**.

## Decisão

### 1. A sessão só roda no aplicativo instalado. O navegador é bloqueado — em código.

Na pilha nativa, o FLAC é decodificado pelo ExoPlayer e devolve o mesmo PCM do WAV; é isso que
sustenta a afirmação de reprodução sem alteração. No navegador, o áudio passa pela pilha do
browser: o `AudioContext` reamostra para a taxa do dispositivo, e o caminho pode aplicar ganho ou
limitação própria. **Ninguém validou isso** — e não é validável de uma vez por todas, porque
depende de navegador, versão e sistema.

Deixar a sessão rodar ali seria coletar dado sobre um estímulo que o estudo **não consegue afirmar
qual é**. Em um estudo cujo instrumento é o áudio, isso não é um risco aceitável: contamina o dado
sem deixar rastro, porque a sessão parece ter funcionado.

O bloqueio é **da sessão, não do aplicativo**. Diário, questionários, linha de base, seguimento,
relato de evento adverso e a tela de senha da equipe (ADR-096) continuam funcionando na web —
nenhum deles depende da fidelidade do áudio, e travá-los faria o participante perder coleta por um
motivo que não existe.

`isWeb` é **injetável** no `HomeScreen`, com `kIsWeb` como padrão. Não é preciosismo de teste:
`kIsWeb` é `const` e o widget test não roda em web, então sem a injeção a trava seria código que
nenhum teste alcança — e trava que ninguém testa é trava que desaparece na primeira refatoração.

Quando o participante é **descontinuado** e está na web, aparece **um** cartão, o da
descontinuação. Duas explicações de "não há sessão" por motivos diferentes, empilhadas, e a
relevante para essa pessoa é a primeira.

### 2. Distribuição: **APK assinado, por link direto**, entregue pela equipe.

O piloto é N≈40, em uma instituição, com etapa presencial já prevista no protocolo (a (i) de
verificação técnica e calibração e a (ii) de usabilidade). Nesse cenário:

- **Play Console (teste interno)** custa US$ 25 uma vez e resolve a instalação sem "fontes
  desconhecidas", mas exige conta, chave gerenciada e um ciclo de publicação para cada correção
  durante um piloto de quatro semanas. Fica **documentado como caminho de upgrade** — a decisão de
  pagar é do mantenedor, e nada no código muda se ele decidir pagar.
- **TestFlight** não se aplica: não há build iOS.
- **Link direto** é o que casa com o tamanho e o prazo do piloto, *desde que* o arquivo tenha
  identidade verificável — que é a parte que faltava.

### 3. O APK passa a ser assinado com chave própria, e o CI diz quando não foi.

O `release.yml` ganhou um passo de assinatura com `apksigner`, a partir de um keystore guardado em
segredo do repositório. Três detalhes deliberados:

- **Sem o segredo, nada quebra** — o build continua saindo, com a chave de debug, como antes. Mas
  o artefato muda de nome para **`sereno-apk-DEBUG-NAO-DISTRIBUIR`**. Um APK de debug com nome
  limpo é exatamente o que alguém baixa com pressa e entrega a um participante.
- **Segredo pela metade falha alto.** Com o keystore presente e uma senha faltando, o passo
  **erra** em vez de cair no caminho de debug — senão o build inteiro passaria e o artefato sairia
  com nome de confiável.
- **A impressão digital SHA-256 do certificado vai para o log**, de propósito. É por ela que a
  equipe confere, antes de distribuir, que o arquivo saiu **dali** e não de outro lugar.

### 4. Android-only **não é emenda de protocolo**.

O critério de inclusão aprovado já diz: *"Smartphone compatível com **a versão distribuída do
aplicativo**"* (ADR-105). A redação é aberta por construção e esta ADR é que a preenche. Ainda
assim, entra na tabela de declarações do dossiê (§4b, item **D5**): o comitê precisa saber que
"compatível" significa Android, porque isso afeta quem pode participar.

## Consequências

- O estudo passa a ter **um único caminho de coleta de sessão**, e é o caminho verificado.
- O app web continua útil e continua publicado — inclusive porque a tela de senha da equipe
  (ADR-096) depende dele.
- A equipe ganha um passo a mais na inclusão: instalar o aplicativo com o participante. Isso já
  acontece de fato na etapa (ii); agora está escrito (`docs/distribuir-o-app.md`).
- **iOS fica fora do piloto.** Um participante sem Android não é elegível — o que precisa estar
  claro no recrutamento, não descoberto na inclusão.
- Enquanto o keystore não existir, o CI produz um artefato marcado como não distribuível. É o
  estado correto: hoje **não há** chave de assinatura, e fingir que há seria pior.

## Alternativas consideradas

**Validar a fidelidade no navegador e liberar a web.** Rejeitada para o piloto, não em definitivo.
Exigiria medir a saída real do browser (captura + FFT) em cada combinação de navegador, versão e
sistema que um participante possa usar — e repetir a cada atualização de browser. É trabalho maior
que o piloto inteiro, para remover uma restrição que não atrapalha o piloto.

**Deixar a web rodar com um aviso.** Rejeitada, e é a alternativa mais tentadora. Um aviso
transfere ao participante uma decisão técnica que ele não tem como avaliar — e o dado entraria no
estudo do mesmo jeito, sem marcação, misturado ao dado válido. Se fosse para aceitar sessões da
web, o mínimo seria registrar a plataforma por sessão e excluí-las da análise primária; aí a
complexidade fica maior que a de simplesmente não coletar.

**Publicar o APK em release do GitHub, público.** Rejeitada por ora: o link ficaria indexável e
qualquer pessoa instalaria o app do estudo. Não há dano direto (sem código de estudo válido não se
entra), mas é superfície desnecessária durante um piloto fechado.

**Assinar dentro do Gradle (`key.properties`).** É o caminho canônico, e foi rejeitado por um
motivo específico deste repositório: as pastas nativas são **geradas no CI** por `flutter create`,
e o arquivo a corrigir muda de nome e de sintaxe conforme a versão do Flutter (`build.gradle` →
`build.gradle.kts`). Assinar o APK pronto com `apksigner` não depende da versão do template.
