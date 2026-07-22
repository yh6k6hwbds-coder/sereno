# Deploy do backend na Fly.io (São Paulo) — passo a passo

Objetivo: colocar a API num endereço HTTPS público (`https://sereno-piloto-api.fly.dev`)
na região **gru (São Paulo)**, para o app funcionar no celular dos participantes.
Decisão e ressalvas em `docs/decisoes/ADR-076-deploy-fly-residencia.md`.

> Os comandos abaixo **você** executa (é sua conta Fly e seu cartão). No Claude Code,
> rode cada um com o prefixo `! ` para a saída cair aqui e eu te ajudar se algo falhar.
> Todos os `fly …` rodam a partir da pasta `sereno/` (onde está o `fly.toml`).

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
