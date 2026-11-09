# Belge işleme işçisini başlatır (metin çıkarma ve OCR). Ctrl+C ile elindeki görevi bitirip durur.

$kok = Split-Path -Parent $PSScriptRoot
Set-Location $kok
$env:DATABASE_URL = [Environment]::GetEnvironmentVariable('DATABASE_URL', 'User')
$env:MUVEKKIL_ANAHTARI = [Environment]::GetEnvironmentVariable('MUVEKKIL_ANAHTARI', 'User')
& "$kok\.venv\Scripts\python.exe" -m app.belge.isci
