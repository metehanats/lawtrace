# API sunucusunu başlatır (http://127.0.0.1:8000). Arayüz /api isteklerini buraya iletir.
# --proxy-headers: arayüz sunucusu üzerinden gelen isteklerde gerçek istemci IP'si denetim kaydına yazılsın.
# Yalnızca yerel arayüz sunucusuna (127.0.0.1) güvenilir.

$kok = Split-Path -Parent $PSScriptRoot
Set-Location $kok
$env:DATABASE_URL = [Environment]::GetEnvironmentVariable('DATABASE_URL', 'User')
$env:MUVEKKIL_ANAHTARI = [Environment]::GetEnvironmentVariable('MUVEKKIL_ANAHTARI', 'User')
& "$kok\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
