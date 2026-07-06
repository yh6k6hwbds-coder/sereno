# tunel.ps1 — sobe o túnel Cloudflare para o backend local e imprime o link do app.
#
# Uso (na pasta sereno/):
#   1) suba o backend:  docker compose up -d
#   2) rode:            powershell -ExecutionPolicy Bypass -File scripts\tunel.ps1
#
# Ele imprime (e copia p/ a área de transferência) o link pronto para abrir no
# celular, já com ?api=<url-do-túnel>. Deixe a janela aberta enquanto usar o app;
# Ctrl+C encerra o túnel. A URL do trycloudflare muda a cada execução — por isso o
# script imprime o link certo toda vez. Ver docs/rodar-por-tunel.md.

$ErrorActionPreference = 'Stop'
$cf    = Join-Path $env:USERPROFILE '.cloudflared\cloudflared.exe'
$pages = 'https://yh6k6hwbds-coder.github.io/sereno/'

if (-not (Test-Path $cf)) {
  Write-Host "cloudflared não encontrado em $cf" -ForegroundColor Red
  Write-Host "Baixe em: https://github.com/cloudflare/cloudflared/releases (windows-amd64) e salve nesse caminho."
  exit 1
}

# Aviso se o backend não estiver de pé (não bloqueia).
try {
  Invoke-WebRequest -Uri 'http://localhost:8000/health' -TimeoutSec 3 -UseBasicParsing | Out-Null
} catch {
  Write-Host "Aviso: http://localhost:8000/health não respondeu. Rode 'docker compose up -d' antes." -ForegroundColor Yellow
}

Write-Host "Subindo túnel para http://localhost:8000 ... (Ctrl+C para encerrar)`n"
$shown = $false

& $cf tunnel --url http://localhost:8000 --no-autoupdate 2>&1 | ForEach-Object {
  $line = "$_"
  $line
  if (-not $shown -and $line -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
    $url  = $Matches[0]
    $link = "$pages" + "?api=$url/v1"
    Write-Host "`n==================================================================" -ForegroundColor Green
    Write-Host " ABRA ESTE LINK NO CELULAR (copiado para a área de transferência):"  -ForegroundColor Green
    Write-Host "   $link" -ForegroundColor Cyan
    Write-Host "==================================================================`n" -ForegroundColor Green
    try { Set-Clipboard -Value $link } catch {}
    $shown = $true
  }
}
