# ADR-108 — Dose de exposição auditiva: a conta, a janela e o alerta dos 50%

- **Status:** Aceito
- **Data:** 2026-08-31
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado
- **Etapas relacionadas:** 2 (player/instrumento), 3 (UX), 5 (backend)
- **Contexto de origem:** item **G9** do `docs/ROADMAP.md`, aberto pelo ADR-101.
- **Relaciona-se com:** ADR-101 (teto de volume; o `audio_gain` por sessão era o insumo que
  faltava), ADR-107 (volume médio/máximo efetivamente aplicado), ADR-106 (`/participants/me/status`,
  por onde a dose sai).

## Contexto

O protocolo, em **"Intensidade e segurança auditiva"**:

> "A exposição total prevista (20 minutos por sessão, 5 sessões semanais, 4 semanas, totalizando
> aproximadamente 6 horas e 40 minutos) situa-se amplamente abaixo da dose semanal de referência
> do padrão de audição segura, equivalente a **80 dB(A) por 40 horas semanais** para adultos
> (OMS; UIT, 2019). **O aplicativo manterá contabilização de dose acumulada e exibirá alerta ao
> atingir 50% do limite de referência.**"

A última frase é uma promessa feita ao CEP e repetida ao participante no TCLE ("a exposição total
prevista fica bem abaixo dos limites de audição segura recomendados pela OMS"). Nada disso existia
no software: não havia contabilização, não havia alerta, e não havia sequer a fórmula.

Três perguntas que o protocolo **não** responde e sem as quais não há implementação:

1. **A dose acumulada de quê, contra que janela?** A referência OMS/UIT é uma *permissão de
   energia sonora por semana* — 80 dB(A) por 40 h, ou 1,6 Pa²h no vocabulário da Recomendação
   UIT-T H.870. Não é um teto vitalício. Comparar quatro semanas de exposição com uma permissão de
   uma semana inflaria o número por construção.
2. **Qual é o nível em dB(A) de uma sessão?** O que o sistema tem é `audio_gain`: um número
   adimensional, "quanto do fundo de escala do arquivo foi reproduzido". Virar dB(A) depende do
   transdutor, e sai da **calibração em acoplador de orelha** — etapa (i) do protocolo, item F2.7
   do roadmap, **ainda não feita**.
3. **Qual troca?** 3 dB (energia) ou 5 dB (norma ocupacional de alguns países)? A escolha muda a
   dose por um fator grande.

## Decisão

**Novo `backend/app/core/hearing.py`** com a conta, separada de quem a consome — do mesmo modo que
`core/protocol.py` guarda os números do calendário e da dose de sessões.

**A troca é de 3 dB** (energia constante): `T(L) = 40 h × 2^((80 − L)/3,0103)`. "3 dB" é o nome
arredondado da regra; a energia dobra exatamente a cada `10·log10(2) = 3,0103` dB, e é esse o valor
da constante — usar 3,00 cravado daria 20,0 h em 83 dB(A) em vez das 20,047 h que a conta de
energia devolve. A troca de 5 dB daria uma dose mais permissiva do que a que o protocolo cita.

**A janela do alerta é MÓVEL, de 7 dias.** É a única janela em que a referência tem significado
audiológico. A soma do estudo inteiro vai junto na resposta (`total_pct`), porque é a "dose
acumulada" que o texto nomeia — mas **não** é o que o alerta observa.

**Conta o tempo efetivo de reprodução**, não a duração do arquivo: quem pausou não se expôs.
Sessão sem `effective_seconds` (aberta, ou nunca encerrada) contribui zero.

**Sem calibração, a dose é PREVISÃO e a resposta diz isso.** `AUDIO_CALIBRATED_SPL_DBA` é o nível
medido em acoplador com o ganho em 1,0, e **não tem default numérico**. Enquanto estiver vazia, o
nível de cada sessão é o **prescrito pelo protocolo** (60 dB(A)) e a resposta carrega
`calibrated: false` + `assumed_spl_dba: 60`. A tela do participante muda de texto conforme o
carimbo. Um valor plausível chutado na config viraria "dose medida" na tela e num relatório ao CEP;
dizer que a medida não existe é melhor do que inventá-la.

Quando a calibração existir, o nível sai do ganho **efetivamente aplicado** (`gain_mean`, ADR-107),
com `L = ref + 20·log10(ganho)` — 20·log10 porque ganho é razão de **amplitude**; usar 10·log10
(razão de potência) subestimaria o nível pela metade em dB.

**Sai por `GET /v1/participants/me/status`**, junto do andamento no protocolo, e não por um
endpoint próprio: a tela inicial já faz essa chamada, e a dose é uma leitura do histórico do
participante como a adesão. **Idêntica nos dois braços** — ativo e sham têm a mesma energia
acústica (inegociável #1), e há teste provando que as duas respostas são iguais.

**Na Home, o cartão só aparece depois da primeira sessão.** "0% da referência" para quem nunca
ouviu nada é ruído, não informação. E percentuais minúsculos não são arredondados para "0%": a
exposição prevista do estudo inteiro é ~0,17% da permissão semanal, que com uma casa inteira leria
como "nada foi contabilizado".

## Consequências

- A afirmação central do parágrafo do protocolo deixou de ser afirmação e virou **conta com
  teste**: 6h40 a 60 dB(A) consomem **0,17%** da permissão semanal, porque em 60 dB(A) são
  permitidas **4000 h** por semana — mais horas do que a semana tem. **O alerta dos 50% não vai
  disparar no piloto**, e é isso que se quer poder demonstrar.
- **A calibração (F2.7) ganhou mais um dependente.** Ela já travava o *valor* do teto de volume
  (G3); agora também decide se a dose é medida ou prevista. O mecanismo dos dois está pronto e
  espera o mesmo número.
- O `AUDIO_CALIBRATED_SPL_DBA` recusa subir com valor fora de `(0, 120]` dB(A): um dBFS digitado
  no lugar de um dB(A) entraria negativo, e uma dose calculada em cima de um erro de unidade é
  pior do que não ter dose.
- **Fora de escopo, deliberadamente:** a exposição do participante a **outros** sons (o mundo, o
  fone que ele usa para música) não é observável pelo app, e a dose exibida é a **do estudo**. O
  texto do alerta diz isso ao sugerir reduzir a exposição a outros sons altos na semana.
- A dose **não** entra no relatório agregado ao CEP nesta fatia. A equipe vê o registro por
  participante só pela API; é a mesma lacuna do painel (lacuna operacional #4).

## Alternativas consideradas

- **Alertar em 50% do acumulado do estudo inteiro.** Recusada: compara energia de 4 semanas com
  uma permissão de 1 semana, e dispararia um alerta que a referência não sustenta.
- **Assumir um dB(A) plausível de fone de ouvido típico e chamar de medida.** Recusada: seria
  apresentar como medido um número que ninguém mediu, num documento que vai ao CEP.
- **Esconder a dose até haver calibração.** Recusada: o protocolo promete exibi-la, e uma
  estimativa rotulada como estimativa cumpre a promessa sem enganar.
- **Calcular a dose no cliente.** Recusada: o histórico de sessões e o nível calibrado são do
  servidor, e o cliente sem rede mostraria uma dose desatualizada como se fosse a atual.
