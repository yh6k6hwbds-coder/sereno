# Deploy do backend na Fly.io (São Paulo) — passo a passo

Objetivo: colocar a API num endereço HTTPS público (`https://sereno-piloto-api.fly.dev`)
na região **gru (São Paulo)**, para o app funcionar no celular dos participantes.
Decisão e ressalvas em `docs/decisoes/ADR-076-deploy-fly-residencia.md`.

> Os comandos abaixo **você** executa (é sua conta Fly e seu cartão). No Claude Code,
> rode cada um com o prefixo `! ` para a saída cair aqui e eu te ajudar se algo falhar.
> Todos os `fly …` rodam a partir da pasta `sereno/` (onde está o `fly.toml`).

> **Este documento é sobre INFRAESTRUTURA** — subir, configurar, agendar. A operação do estudo no
> dia a dia (inscrever, alocar, acompanhar, responder a evento adverso, exportar) está no
> **`operar-o-estudo.md`**, escrito para quem não programa.

## Ordem de execução (a Fase F3 inteira, em sequência)

As dez pendências operacionais do `ROADMAP.md` §F3 nesta ordem — cada uma com o que a destrava e
onde está a receita. **Todo o código já existe e está testado**; o que falta aqui é credencial,
infraestrutura ou alguém agendar. Marque conforme for.

| Ordem | Item | Depende de | Onde | Sem isto |
|---|---|---|---|---|
| 1 | **SMTP real** (F3.2) | Credencial — o NIT pode indicar um provedor já contratado | "Antes de participantes reais" | O OTP não chega e **ninguém consegue entrar** |
| 2 | **Deploy na Fly** (F3.3) | Cartão na conta Fly | §0–§3 | Só existe o ambiente local/túnel |
| 3 | **Chave selada A/B** (`ARM_CONDITION_MAP`) | Sorteio decidido e custodiado fora do sistema | §2 | O guard **recusa subir** em produção |
| 4 | **`STAFF_SETUP_URL`** (F3.10) | App publicado no GitHub Pages | §3.3 | O convite da equipe manda o token cru |
| 4b | **A PRIMEIRA conta de staff** (H3) | Só o deploy no ar | §3.35 | **Ninguém entra**: criar staff exige `user:manage`, que só staff tem |
| 5 | **`TEAM_NOTIFY_EMAIL`** (F3.7) | Um endereço da equipe | §3.2 | O alerta só vai para o log — ninguém vê |
| 6 | **Agendar o expurgo (F3.1) E a varredura (F3.11)** — dois scripts, mesmo agendador | Deploy no ar (ou um host externo) | §3.1 e §3.5 | Os mecanismos existem e **nunca rodam**: item E2 do checklist LGPD aberto, e a regra da 2ª semana não alcança quem parou de abrir o app |
| 7 | **Worker de e-mail** (F3.8) | Redis + processo `worker` no `fly.toml` | §3.2 | ⚠️ Ligar `EMAIL_DELIVERY=queue` **sem worker** para o OTP de vez |
| 8 | **Vault** (F3.9) | Um Vault hospedado, chave com `derived=true` | §3.2 | A custódia da chave **não mudou** na prática (C11 aberto) |
| 9 | **Pentest externo** (F3.5) | Decisão/contratação do NIT | — | Nenhuma revisão independente antes de dado real |
| 10 | **Versão `1.0.0` do TCLE** (F3.4) | **Parecer do CEP** | `python scripts/tcle_version.py 1.0.0` | O termo segue marcado como rascunho, corretamente |

> **Os itens 1–8 são de infraestrutura e podem ser feitos a qualquer momento** — inclusive antes das
> aprovações, para que o ambiente esteja pronto. **Nenhum deles autoriza coletar dado real:** isso
> depende da base legal (F1.1), que não se resolve aqui. Ver `solicitacao-nit-base-legal.md`.
>
> **O item 10 não é "uma linha em cada arquivo"**, como o roadmap dizia. São quatro literais em três
> linguagens, mais um teste de widget que guarda o estado de rascunho de propósito e **vai falhar**.
> `scripts/tcle_version.py` faz a parte mecânica e imprime o resto; `--check` roda no CI e impede
> que backend e app se separem sem ninguém notar.

## 0. Instalar o flyctl (uma vez) e entrar

```powershell
# Instalar (PowerShell):
iwr https://fly.io/install.ps1 -useb | iex
# Reabra o terminal. Depois:
fly version
fly auth signup   # (ou `fly auth login` se já tiver conta) — pede cartão
```

## 1. Criar o app e o Postgres em São Paulo

```powershell
fly apps create sereno-piloto-api
fly postgres create --name sereno-piloto-db --region gru
#   -> escolha o plano "Development" (single node) para o piloto.
fly postgres attach sereno-piloto-db --app sereno-piloto-api
#   -> isto injeta a secret DATABASE_URL no app automaticamente.
```

## 2. Definir os segredos da aplicação

Gere segredos fortes (PowerShell) e cole no comando seguinte:

```powershell
function New-Key { $b = New-Object byte[] 32; `
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); `
  [Convert]::ToBase64String($b) }
"JWT_SECRET     = $(New-Key)"
"PII_ENC_KEY    = $(New-Key)"
"ALLOCATION_SEED= $(New-Key)"
```

```powershell
fly secrets set `
  JWT_SECRET="<cole>" `
  PII_ENC_KEY="<cole>" `
  ALLOCATION_SEED="<cole>" `
  ARM_CONDITION_MAP="A:sham,B:active" `
  --app sereno-piloto-api
```

> **Chave selada (`ARM_CONDITION_MAP`) — obrigatória.** É o mapa braço→condição. `fly.toml`
> liga `APP_ENV=production`, e o **guard de startup recusa subir** se ela não estiver setada
> (senão o braço codificado A/B, que sai no export, revelaria ativo/sham — inegociável #2).
> O valor é um **sorteio** decidido e custodiado por fora (tipicamente a orientadora):
> `A:sham,B:active` **ou** `A:active,B:sham`. Anote-o offline; só se abre no *data lock*.
> `CORS_ORIGINS` e `APP_ENV` (não-segredos) vêm do `fly.toml`. Não coloque segredos no `fly.toml`.

## 3. Deploy e verificação

```powershell
fly deploy --app sereno-piloto-api
# A imagem é buildada do backend/Dockerfile; o entrypoint roda `alembic upgrade head`.
curl https://sereno-piloto-api.fly.dev/health      # liveness: {"status":"ok"}
curl -i https://sereno-piloto-api.fly.dev/ready    # prontidão real: 200 {"status":"ready", "checks":{...}}
```

> **`/health` vs `/ready` (ADR-090).** O health check do `fly.toml` aponta para **`/health`**
> (liveness: o processo está de pé) e assim deve continuar **enquanto houver 1 réplica só** —
> `/ready` reprova (503) quando o banco cai, e com réplica única isso tiraria a app inteira do
> balanceador durante um soluço do Postgres, trocando "erro em algumas requisições" por
> "indisponível". **A partir de 2 réplicas, mude o check para `/ready`**: aí retirar a réplica doente
> da rotação é exatamente o comportamento desejado, e as outras absorvem o tráfego. `/ready` também
> serve para diagnóstico manual a qualquer momento: `checks.redis = "down"` com `status = "degraded"`
> indica Redis fora em postura fail-open (ADR-079) — a app funciona, o rate limit está frouxo.

Semear dados de demo para testar o login (opcional, dados sintéticos):

```powershell
fly ssh console --app sereno-piloto-api -C "python scripts/seed_demo.py"
# Código de estudo = DEMO.
```

> **OTP em produção não sai no log.** Com `APP_ENV=production` o guard proíbe
> `EMAIL_DEV_CONSOLE`; sem SMTP configurado o código não é entregue (`NullEmailSender` —
> não vaza, mas ninguém recebe). Para smoke-test rápido com OTP-no-console, rode **local**
> (`docker compose`, `APP_ENV=dev`, `EMAIL_DEV_CONSOLE=1`) ou pelo túnel — não na Fly de
> produção. Para testar o login na Fly, configure o SMTP real (seção "Antes de participantes").

## 3.1. Agendar o expurgo de transitórios (retenção, E2/ADR-091/094)

A política de retenção classifica os desafios de OTP como **transitórios** (expurgo diário, nunca
> 24 h). O mesmo job também apaga os **tokens de convite/redefinição de senha de staff**
(`staff_setup_token`, ADR-094). O mecanismo está pronto e testado — **falta alguém chamá-lo
periodicamente**. Enquanto não for agendado, o expurgo simplesmente não acontece, e o item E2 do
checklist LGPD segue aberto.

```powershell
# Execução manual / verificação (não apaga nada com --dry-run):
fly ssh console --app sereno-piloto-api -C "python scripts/purge_otp.py --dry-run"
fly ssh console --app sereno-piloto-api -C "python scripts/purge_otp.py"
# Saída: {"deleted": N, "remaining": M, "staff_tokens_deleted": K, "grace_min": 60, "dry_run": false}
```

**Opções de agendamento** (escolher uma, `[a definir com o mantenedor]`):
- **Cron externo** (a máquina do mantenedor, um runner de CI agendado, qualquer host): invoca o
  `fly ssh console -C` acima uma vez por dia. Mais simples; depende de um host de fora estar de pé.
- **Máquina agendada da Fly** (`fly machine run ... --schedule daily`): roda dentro da própria
  infraestrutura, sem depender de host externo. Preferível quando o deploy estiver de fato no ar.

O script sai com **código ≠ 0 em falha**, então qualquer agendador consegue alertar. É idempotente
— rodar duas vezes seguidas apaga 0 na segunda; rodar com frequência maior que a diária é inofensivo.

## 3.2. Ligar alertas, worker de e-mail e cofre (F3.7–F3.9)

Três mecanismos prontos que **só valem se alguém os ligar no ambiente**. Nenhum é obrigatório para
subir; todos importam antes de dado real.

```powershell
# Alertas automáticos (ADR-093) — sem destino, o aviso só vai para o log:
fly secrets set --app sereno-piloto-api TEAM_NOTIFY_EMAIL="equipe@uninta.edu.br"

# Fila durável de e-mail (ADR-092) — precisa de Redis E de um processo worker:
fly secrets set --app sereno-piloto-api EMAIL_DELIVERY=queue
#   No fly.toml, um [processes] extra:  worker = "python scripts/email_worker.py"
#   ATENÇÃO: com EMAIL_DELIVERY=queue e NENHUM worker, os e-mails ficam parados na fila
#   e o OTP nunca chega — verifique o worker antes de trocar o modo.

# Custódia da chave de PII no cofre (ADR-095) — exige um Vault hospedado:
#   vault write -f transit/keys/sereno-pii-kek derived=true   <- sem derived=true a
#   amarração participante+campo some SEM ERRO VISÍVEL
fly secrets set --app sereno-piloto-api KEY_PROVIDER=vault VAULT_ADDR=... VAULT_TOKEN=...
```

> ⚠️ O deploy da Fly **não tem Redis nem Vault** hoje (`fly.toml` sobe 1 instância sem Redis).
> `EMAIL_DELIVERY=queue` e `KEY_PROVIDER=vault` pressupõem que essa infraestrutura exista.

## 3.3. Apontar o convite de staff para o app publicado (F3.10)

O convite e a redefinição de senha da equipe são feitos por **link de uso único** (ADR-094), e a
tela que recebe esse link vive no **próprio app web** (ADR-096): com `?token=` na URL, o app abre a
tela de definir senha em vez do login do participante. **Sem `STAFF_SETUP_URL`, o e-mail sai com o
token cru** e a pessoa precisa montar um `POST` na mão — o fluxo existe, mas ninguém que não seja
técnico consegue usá-lo.

```powershell
# Aponte para a RAIZ do app publicado (GitHub Pages), com a barra final:
fly secrets set --app sereno-piloto-api `
  STAFF_SETUP_URL="https://<usuario>.github.io/sereno/" `
  STAFF_SETUP_PEPPER="<cole um segredo forte — mesma disciplina do OTP_PEPPER>"
```

> **Não monte o `?token=` você mesmo.** O backend acrescenta o parâmetro respeitando query já
> existente (`?api=<túnel>/v1` da demo vira `...&token=...`). Uma URL terminada em `?` ou já com
> `token=` produz link quebrado.
>
> **A URL tem de ser a versão publicada do app.** Apontar para um build local ou para uma versão
> antiga entrega ao convidado uma tela que não fala com esta API — e o token queima na tentativa.

Verificação ponta a ponta (depois do SMTP configurado): crie um staff sem senha
(`POST /v1/staff` sem `password`), confirme que o e-mail chegou **com link clicável**, abra-o e
defina a senha. O token some da barra de endereços ao carregar a tela.

## 3.35. A PRIMEIRA conta de staff (H3, ADR-112) — sem isto ninguém entra

`POST /v1/staff` exige a permissão `user:manage`, que **só um staff já existente tem**. A tabela
nasce vazia na migração inicial e o `seed_demo.py` não cria staff. Banco novo = **sistema em que
ninguém entra**, e não havia passo nenhum para isso até a Fase H.

```bash
fly ssh console --app sereno-piloto-api -C \
  "python scripts/bootstrap_staff.py --email ana@uninta.edu.br --email bruno@uninta.edu.br --print-link"
```

**Duas contas, não uma.** O descegamento exige **dois admins distintos** (ADR-075). Uma instalação
com um admin só descobre isso no fim do estudo, na hora de abrir a chave selada — quando o
conserto é mais caro. O `--check` cobra o segundo:

```bash
fly ssh console --app sereno-piloto-api -C "python scripts/bootstrap_staff.py --check"
```

> **O script nunca define senha.** Cada conta nasce com um hash de senha aleatória que ninguém
> conhece e recebe um **token de uso único** para a própria pessoa definir a sua — a mesma
> disciplina do ADR-094. Um `--password` na linha de comando entraria no histórico do shell e nos
> logs do provedor; e quem opera o deploy ganharia caminho para entrar como outra pessoa.
>
> **`--print-link` é o caminho ANTES do SMTP (item 1 da ordem).** Sem e-mail configurado, o
> convite não chega e o bootstrap seria impossível justamente quando é necessário. Com a flag, o
> link sai no seu terminal: **é segredo**, vale uma vez, expira (`STAFF_INVITE_TTL_H`, padrão no
> `setup_service`) e **não deve ser colado em chat, ticket ou registro de deploy**.
>
> **Faça isto DEPOIS do §3.3** (`STAFF_SETUP_URL`): sem ela, o link impresso é o token cru, e a
> pessoa precisa montar um `POST` na mão.
>
> Havendo staff, o script **se recusa** a agir — dali em diante o caminho é `POST /v1/staff`, que
> registra quem convidou quem. `--force` existe para o caso real da instalação que ficou com um
> admin só e ninguém consegue entrar.

## 3.4. Áudio: formato, disco e primeira materialização (ADR-103)

Nada a configurar no caminho feliz — mas três coisas quebram em produção se passarem batido:

1. **`AUDIO_FORMAT` fica em `flac`** (padrão). Em `wav` cada participante baixa **230 MB por
   protocolo**; use-o só para depurar. Trocar o valor **invalida o cache** (a extensão faz parte
   do nome do arquivo) e muda o `ETag`, então todo aparelho rebaixa o áudio uma vez.
2. **`libsndfile` precisa existir na imagem** — o `backend/Dockerfile` já instala `libsndfile1`,
   e as wheels de `soundfile` trazem a biblioteca embutida. Faltando, a materialização **falha
   alto** (`EncoderUnavailable`) em vez de servir WAV gigante em silêncio.
3. **Disco para o cache.** `AUDIO_CACHE_DIR` (padrão `<backend>/.audio_cache`) guarda um arquivo
   por protocolo: ~33 MB cada em FLAC, mais o sidecar `.sha256`. Em máquina com sistema de
   arquivos efêmero o primeiro acesso de cada boot **rematerializa** (síntese de 20 min ≈ dezenas
   de segundos e um pico de CPU); para evitar isso, monte um volume ou rode
   `python scripts/seed_protocols.py` e faça um `GET` de cada protocolo logo após o deploy.

```bash
fly ssh console -C "python -c 'import soundfile; print(soundfile.__libsndfile_version__)'"
```

## 3.5. Agendar a varredura de descontinuação (F3.11 / G6, ADR-106)

O protocolo descontinua quem, **ao final da 2ª semana**, concluiu menos de 50% das sessões
previstas até ali. O servidor aplica a regra sozinho quando o participante abre a tela inicial ou
tenta iniciar uma sessão — mas isso, por construção, **nunca alcança quem parou de abrir o
aplicativo**, que é exatamente o caso que a regra existe para pegar. Por isso existe a varredura:

```bash
# Semanalmente. Idempotente: rodar de novo devolve discontinued: 0.
fly ssh console --app sereno-piloto-api -C "python scripts/sweep_discontinuations.py"
# -> {"evaluated_at": "...", "discontinued": 2, "dry_run": false}
```

**Exatamente o mesmo agendamento do §3.1 (expurgo) — resolva os dois juntos.** Os dois são
scripts que rodam dentro do servidor, sem credencial nenhuma.

> **Por que script, e não a chamada HTTP.** O endpoint `POST /v1/discontinuations/evaluate`
> continua existindo e é o caminho quando **uma pessoa** quer rodar a varredura na hora. Mas ele
> exige token de staff, e o login de staff exige **MFA** — de propósito. Agendar a chamada
> obrigaria a guardar credencial **e** segredo de segundo fator no agendador, esvaziando o MFA
> para ganhar uma tarefa de rotina. Os dois caminhos chamam a **mesma** função de serviço: a regra
> vive em um lugar só.
>
> `--dry-run` diz quantos *seriam* descontinuados sem gravar nada — útil na primeira vez.
> A saída **não nomeia participante**: log de agendador é lido por quem opera infraestrutura, e
> a lista com nome de estudo sai pelo `GET /v1/discontinuations`.

**Antes de agendar, confirme com a equipe** (a lista sai em `GET /v1/discontinuations`): a
descontinuação **para as sessões** do participante. Ela não apaga nada — o participante segue na
análise por intenção de tratar — mas alguém deve entrar em contato, e é a equipe que faz isso.

## 4. Reconstruir o app apontando para a API pública

O CI já injeta a URL. O default (`https://sereno-piloto-api.fly.dev/v1`) casa com o
nome do app acima — se você mudou o nome, ajuste a variável do repositório:

```powershell
# (só se mudou o nome do app)
gh variable set API_BASE_URL --body "https://<seu-app>.fly.dev/v1"
```

Dispare o rebuild do app (web no GitHub Pages + APK como artefato):

```powershell
gh workflow run "Build & Deploy (app)"
# ou simplesmente faça um push para master.
```

Ao terminar: abra a URL do GitHub Pages (Settings > Pages) no celular. O login com **DEMO**
na Fly exige SMTP configurado (abaixo); sem ele, teste o login localmente/por túnel em dev.
O APK fica em Actions > run > Artifacts.

## Antes de participantes reais (não pular)

- **SMTP real** (obrigatório p/ o OTP chegar): `fly secrets set SMTP_HOST=... SMTP_USER=...
  SMTP_PASSWORD=... SMTP_FROM=...`. Porta **587** usa STARTTLS (default); **465** usa SSL
  implícito (autodetectado; ou force `SMTP_USE_SSL=1`). Opção grátis p/ N≈40: Gmail com
  *app password* (587). `EMAIL_DEV_CONSOLE` **não** funciona em produção (o guard recusa).
- **Rate limit por IP real (já configurado):** o `fly.toml` liga `CLIENT_IP_HEADER=Fly-Client-IP`.
  A Fly injeta/sobrescreve esse cabeçalho com o IP real do participante (à prova de spoof), então
  o limite de OTP/login vale **por cliente** e não por IP da borda (senão viraria um bucket global —
  ADR-064/ADR-078). Se um dia sair da Fly, troque por `TRUSTED_PROXY_HOPS=<nº de proxies>`.
- Validar com orientador/NIT a adequação LGPD/residência (ver ADR-076).
- Definir backups/retenção do Postgres e **custódia da chave selada A/B→condição** (ADR-077):
  quem sabe o sorteio, onde está anotado, e que só se abre no *data lock*.
