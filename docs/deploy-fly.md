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
  --app sereno-piloto-api
```

> `ARM_CONDITION_MAP`, `CORS_ORIGINS` e `EMAIL_DEV_CONSOLE=1` (OTP no log, só teste)
> já vêm do `fly.toml`. Não coloque segredos no `fly.toml`.

## 3. Deploy e verificação

```powershell
fly deploy --app sereno-piloto-api
# A imagem é buildada do backend/Dockerfile; o entrypoint roda `alembic upgrade head`.
curl https://sereno-piloto-api.fly.dev/health      # deve responder {"status":"ok"}
```

Semear dados de demo para testar o login (opcional, dados sintéticos):

```powershell
fly ssh console --app sereno-piloto-api -C "python scripts/seed_demo.py"
# Código de estudo = DEMO. O OTP aparece em: fly logs --app sereno-piloto-api
```

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

Ao terminar: abra a URL do GitHub Pages (Settings > Pages) no celular, use o código
**DEMO**, pegue o OTP em `fly logs` e navegue. O APK fica em Actions > run > Artifacts.

## Antes de participantes reais (não pular)

- Configurar SMTP real (`fly secrets set SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=...`)
  e **remover** `EMAIL_DEV_CONSOLE` do `fly.toml` — senão o OTP não chega por e-mail.
- Validar com orientador/NIT a adequação LGPD/residência (ver ADR-076).
- Definir backups/retenção do Postgres e custódia da chave A/B→condição.
