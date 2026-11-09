# Arayüzü geliştirme kipinde başlatır: http://localhost:3000
# API sunucusunun (calistir\api.ps1) ayrıca çalışıyor olması gerekir.

$kok = Split-Path -Parent $PSScriptRoot
Set-Location "$kok\frontend"
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (Test-Path node_modules)) { npm install --no-fund --no-audit }
npm run dev
