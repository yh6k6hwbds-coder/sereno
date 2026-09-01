# Operar o estudo — receituário da equipe

> **Para quem é isto.** A equipe do Sereno não é de programadores, e **não existe painel gráfico
> de staff** — foi decisão deliberada (ADR-096), para não construir e manter uma interface inteira
> antes do piloto. Toda a operação é por **API**. Este documento existe para que isso não signifique
> "só quem programa consegue operar o estudo".
>
> O `deploy-fly.md` cobre a **infraestrutura** (subir, configurar, agendar). Aqui é a **operação
> do dia a dia**: inscrever, alocar, acompanhar, responder a evento adverso, exportar.
>
> **Este documento não autoriza coletar dado real.** Isso depende da base legal (F1.1) e do
> parecer do CEP. Ver `solicitacao-nit-base-legal.md`.

## Antes de tudo: como executar os comandos

Os exemplos usam `curl`, que já vem no Windows 10/11 (PowerShell) e no macOS/Linux. Substitua
`$API` pelo endereço da API do estudo e `$T` pelo seu token (a próxima seção explica como obter).

```powershell
$API = "https://sereno-piloto-api.fly.dev/v1"
```

> **Uma alternativa mais confortável:** a API publica a própria documentação navegável em
> `https://<endereço-da-api>/docs`. Dá para entrar, colar o token uma vez em **Authorize** e
> executar qualquer operação por formulário, sem digitar `curl`. **É o caminho recomendado para
> quem não usa terminal** — este documento continua útil como referência do que fazer e por quê.

---

## 1. Entrar (login com segundo fator)

O login da equipe tem **dois passos**, sempre: senha e depois o código de 6 dígitos do app
autenticador. O segundo fator é **obrigatório** — não há como desligá-lo.

```bash
# Passo 1 — senha. A resposta NÃO é o acesso ainda.
curl -sX POST "$API/auth/token" -H "Content-Type: application/json" \
  -d '{"email":"voce@uninta.edu.br","password":"sua-senha"}'
```

A resposta traz um de três desfechos:

| O que veio | O que significa | O que fazer |
|---|---|---|
| `mfa_required: true` + `mfa_token` | Tudo certo, falta o 2º fator | Passo 2, abaixo |
| `mfa_enrollment_required: true` + `enrollment_token` | **Primeiro acesso**: o MFA ainda não foi configurado | Seção 1.1 |
| `401` | Senha errada — ou a conta está desativada | Peça uma redefinição a um admin |

```bash
# Passo 2 — o código de 6 dígitos do app autenticador.
curl -sX POST "$API/auth/mfa/verify" -H "Content-Type: application/json" \
  -d '{"mfa_token":"<o mfa_token do passo 1>","code":"123456"}'
```

Agora sim: guarde o `access_token` da resposta em `$T`. Ele **expira** — quando as chamadas
começarem a responder `401`, repita o login.

### 1.1. Primeiro acesso (configurar o segundo fator)

Quem recebeu o convite já definiu a senha pelo link de uso único. Falta o MFA:

```bash
# Com o enrollment_token no lugar do token normal:
curl -sX POST "$API/staff/me/mfa/enroll" -H "Authorization: Bearer <enrollment_token>"
```

A resposta traz `provisioning_uri` (um `otpauth://...`, que vira QR Code) e `secret` (para
digitar à mão). Cadastre no app autenticador — Google Authenticator, Authy, 1Password, o que a
instituição usar — e confirme:

```bash
curl -sX POST "$API/staff/me/mfa/confirm" -H "Authorization: Bearer <enrollment_token>" \
  -H "Content-Type: application/json" -d '{"code":"123456"}'
```

> **O `enrollment_token` não serve para mais nada.** Ele só abre estas duas chamadas — não lê
> dado do estudo. É de propósito: MFA é obrigatório para staff, e um token que já desse acesso
> pleno tornaria o cadastro opcional na prática.

---

## 2. O funil de inscrição, na ordem

Cada passo depende do anterior. Fora de ordem, o servidor recusa — e essa recusa é proteção do
estudo, não um obstáculo a contornar.

### 2.1. Registrar o contato do participante

```bash
curl -sX POST "$API/participants/<id>/contact" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"name":"Nome Sobrenome","email":"pessoa@exemplo.com"}'
```

Nome e e-mail são gravados **cifrados** e separados do dado de pesquisa. A resposta é neutra e
**não ecoa o que você mandou** — se precisar conferir, é sinal de que algo deve ser corrigido, não
lido de volta. Sem contato, o participante não recebe o código de acesso.

### 2.2. Triagem (elegibilidade)

Consulte primeiro os critérios **em vigor** — eles vêm do protocolo aprovado e mudam com emenda,
não com uma conversa:

```bash
curl -s "$API/screening/criteria" -H "Authorization: Bearer $T"
```

Depois envie a triagem com o **conjunto completo** das chaves que a lista devolveu:

```bash
curl -sX POST "$API/screening" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"participant_id":"<id>","inclusion":{...},"exclusion":{...}}'
```

> **Chave faltando é `422`, não "não".** Uma triagem incompleta seria uma decisão de
> elegibilidade tomada sem os dados — o servidor prefere recusar a adivinhar. Duas chaves são
> **derivadas** e o servidor as calcula sozinho a partir dos escores (`sintomas_elegiveis` e a
> alínea (d)): mandá-las também dá 422.

### 2.3. Alocação (randomização)

```bash
curl -sX POST "$API/allocation" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" -d '{"participant_id":"<id>"}'
```

> **A resposta é neutra de propósito e NUNCA diz o braço.** Não é omissão a corrigir: é o
> cegamento. Nem você, nem a pesquisadora, nem o participante sabem em que braço ele caiu — e o
> estudo depende disso continuar assim até o fim.

---

## 3. Acompanhar o estudo (as cinco listas)

Estas são as perguntas do dia a dia. Todas aceitam `?limit=`, mas **o limite não é o mesmo em
todas** — a de participantes pagina por cursor e usa outra escala:

| Pergunta | Chamada | `limit` |
|---|---|---|
| Quem está no estudo, em que pé? | `GET /research/participants` | padrão 20, máx. 200 |
| **O que ainda está em aberto em segurança?** | `GET /adverse-events?pending=true` | padrão 100, máx. 500 |
| O que aconteceu nas sessões? | `GET /sessions/registry` | padrão 100, máx. 500 |
| Quem precisou de encaminhamento? | `GET /referrals` | padrão 100, máx. 500 |
| Quem saiu do protocolo, e por quê? | `GET /discontinuations` | padrão 100, máx. 500 |

```bash
curl -s "$API/research/participants" -H "Authorization: Bearer $T"
curl -s "$API/adverse-events?pending=true" -H "Authorization: Bearer $T"
curl -s "$API/sessions/registry?study_code=P-014" -H "Authorization: Bearer $T"
```

**O que você vai ver — e o que não vai.** Todas trazem o **código do estudo** (`P-014`), nunca
nome ou e-mail. A lista de participantes traz o braço **codificado** (`A`/`B`), que **não diz qual
é o ativo**; `null` significa "inscrito e ainda não randomizado". O registro por sessão **não traz
nada do áudio**, e isso é deliberado: só existem dois protocolos, um por braço, então qualquer
identificador do arquivo agruparia os participantes por braço.

> **`GET /research/participants` pagina por cursor.** Se a resposta trouxer `next_cursor`
> preenchido, há mais páginas: repita a chamada com `?cursor=<o valor>`. `null` = acabou.

---

## 4. Evento adverso: o que fazer

**Segurança é desfecho primário do estudo.** Isto tem prioridade sobre qualquer outra tarefa desta
página.

Quando um evento **moderado ou grave** é relatado, a equipe recebe um e-mail (se
`TEAM_NOTIFY_EMAIL` estiver configurado). O e-mail **não traz o relato** — dado de saúde não sai
por e-mail. Ele avisa; a leitura é aqui:

```bash
# 1. Veja o que está em aberto (moderado/grave ainda sem desfecho registrado).
curl -s "$API/adverse-events?pending=true" -H "Authorization: Bearer $T"

# 2. Conduza o caso conforme o protocolo (é decisão clínica, não de software).

# 3. Registre o desfecho — é isto que FECHA o acompanhamento.
curl -sX POST "$API/adverse-events/<id>/outcome" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"outcome":"resolvido em 24h, sem conduta adicional"}'
```

> **Registrar o desfecho não é burocracia.** É o que o CEP espera de um desfecho primário: cada
> evento acompanhado **até a resolução**. Enquanto não houver desfecho, o evento continua na lista
> de pendentes — que é exatamente o objetivo.
>
> O desfecho **pode ser reescrito** conforme o caso evolui ("em acompanhamento" → "resolvido").
> Não abra um evento novo para corrigir uma frase: isso duplicaria a contagem justamente na tabela
> em que contar eventos importa.

**Se o evento contraindicar a continuidade**, registre a descontinuação — o participante
**permanece na análise** (intenção de tratar), o que é diferente de retirar o consentimento:

```bash
curl -sX POST "$API/participants/<id>/discontinue" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"reason":"evento_adverso","adverse_event_id":"<id do evento>"}'
```

---

## 5. Encaminhamento (PHQ-9)

Quando a avaliação de segurança dispara, o sistema abre uma **ficha** sozinho e retira a pessoa do
protocolo. A equipe tem dois passos a documentar — e o protocolo exige os dois **por escrito**:

```bash
curl -s "$API/referrals" -H "Authorization: Bearer $T"

curl -sX POST "$API/referrals/<id>/record" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"service":"caps","acknowledged":true}'
```

`service` aceita `apoio_institucional`, `caps`, `urgencia` ou `outro`. `acknowledged: true` marca
a **confirmação de acolhimento** — que o serviço de fato recebeu a pessoa, não só que ela foi
encaminhada.

> **A tela do participante nunca mostra o escore.** Um número de gravidade sem profissional junto
> é lido como diagnóstico. O escore fica com a equipe.

---

## 6. Rotinas semanais

**Varredura de descontinuação.** A regra de adesão da 2ª semana só alcança quem **abre o app**. A
varredura alcança quem sumiu — que é justamente quem interessa:

```bash
curl -sX POST "$API/discontinuations/evaluate" -H "Authorization: Bearer $T"
```

> Idealmente isto é **agendado** (F3.11), não lembrado. Enquanto ninguém agendar, alguém precisa
> rodar toda semana. É a mesma pendência do expurgo de transitórios.

**Conferir se há pendências de segurança:** `GET /adverse-events?pending=true` deve devolver lista
vazia ao fim da semana.

---

## 7. Exportar para análise

```bash
# Responde 202 com {"job_id": "...", "status": "..."} — a exportação roda em segundo plano.
curl -sX POST "$API/research/export" -H "Authorization: Bearer $T"

# Enquanto processa, devolve JSON com o status. Quando termina, devolve o CSV:
curl -s "$API/research/export/<job_id>" -H "Authorization: Bearer $T" -o sereno_export.csv
```

> Se o arquivo salvo abrir como JSON (`{"job_id": ..., "status": ...}`) em vez de planilha, a
> exportação **ainda não terminou** — repita a chamada. Não é erro.

O dataset é **pseudonimizado e cego** (braço codificado A/B). O relatório de análise pronto está
em `GET /research/analysis` — exploratório, e **não decide eficácia**: o piloto é de viabilidade.

---

## 8. Descegamento — o que NUNCA é rotina

Abrir o braço exige **dois administradores distintos**, em duas chamadas:

```bash
# Admin 1 — solicita. NÃO revela nada.
curl -sX POST "$API/allocation/<id>/unblind-request" -H "Authorization: Bearer $T_ADMIN1" \
  -H "Content-Type: application/json" \
  -d '{"justification":"emergencia clinica: <descreva o caso>"}'

# Admin 2 (pessoa DIFERENTE) — aprova. Só aqui a condição aparece.
curl -sX POST "$API/allocation/<id>/unblind-approve" -H "Authorization: Bearer $T_ADMIN2"
```

> **Dois admins não é formalidade.** É o que impede que uma curiosidade, uma pressa ou uma pressão
> isolada quebrem o cegamento do estudo inteiro. Tudo fica na trilha de auditoria, que é
> **append-only** — não dá para apagar depois.
>
> Descegamento fora do *data lock* é **emergência clínica**, não conveniência de análise.

---

## 9. Contas da equipe

```bash
curl -s "$API/staff" -H "Authorization: Bearer $T_ADMIN"                       # listar

curl -sX POST "$API/staff" -H "Authorization: Bearer $T_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"email":"nova.pessoa@uninta.edu.br","role":"researcher"}'               # convidar

curl -sX POST "$API/staff/<id>/password-reset" -H "Authorization: Bearer $T_ADMIN"
curl -sX POST "$API/staff/<id>/deactivate"     -H "Authorization: Bearer $T_ADMIN"
```

> **Convide sem `password`.** A pessoa recebe um link de uso único e define a própria senha —
> ninguém escolhe a senha de outra pessoa, nem o admin. A redefinição funciona igual: destrava
> quem perdeu o acesso **sem** dar a ninguém um caminho para entrar como ela. Nenhuma delas mexe
> no MFA.
>
> **Papéis:** `researcher` lê o estudo e inscreve; `admin` faz isso e mais **gerir contas** e
> **descegar**. Nenhum papel revela o braço — nem o de admin, fora do rito da seção 8.

A primeira conta de todas é criada no servidor, no deploy — veja `deploy-fly.md` §3.35.

---

## 10. Direitos do titular (LGPD)

```bash
curl -s  "$API/participants/<id>/data"  -H "Authorization: Bearer $T_ADMIN"   # acesso
curl -sX POST "$API/participants/<id>/erase" -H "Authorization: Bearer $T_ADMIN"  # eliminação
```

> **Eliminar não é o mesmo que retirar o consentimento.** A retirada o próprio participante faz
> pelo app, e é irreversível. A eliminação apaga o **dado pessoal**; o que pode ser mantido, e por
> quanto tempo, é decisão registrada no RIPD e no parecer do CEP — **confirme antes de executar**,
> porque não há desfazer.

---

## Quando algo dá errado

| Resposta | O que costuma ser |
|---|---|
| `401` | Token expirado — refaça o login (seção 1) |
| `403` | Seu papel não tem essa permissão (ex.: `researcher` tentando gerir contas) |
| `404` | Identificador errado — confira o código do estudo na lista de participantes |
| `409` | O passo já foi dado (ex.: participante já alocado ou já descontinuado) |
| `422` | Falta campo ou o valor não é aceito — a resposta diz qual, no campo `detail` |
| `429` | Chamadas demais em pouco tempo; espere e repita |

Toda resposta de erro segue o mesmo formato (`problem+json`) e traz `title` e `detail` em
português. **Leia o `detail` antes de repetir a chamada** — quase sempre ele diz exatamente o que
falta.

Se o erro não fizer sentido, ou uma chamada devolver algo que contradiga este documento, **não
insista nem contorne**: registre o que aconteceu e leve à coordenação. Em um estudo cego, uma
tentativa repetida "para ver se passa" pode ser exatamente o que não deveria ter acontecido.
