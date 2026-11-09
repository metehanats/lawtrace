# Yedek alır, hemen tam doğrular (geçici veritabanına geri yükleyip her belgeyi çözer),
# en yeni 14 yedeği tutar ve sonucu yedek-gunlugu.jsonl dosyasına yazar.
# Zamanlanmış görev (yedek-gorevi.ps1) bu betiği çalıştırır; elle de çalıştırılabilir.
# Veritabanı kapalıysa açar ve iş bitince yeniden kapatır.
# Hedef klasör YEDEK_KLASORU ile değiştirilebilir (ör. harici disk).
# Yedeği açmak için şifreleme anahtarı gerekir; anahtar yedekle aynı yerde saklanmamalıdır.

param([int]$Sakla = 14)

$kok = Split-Path -Parent $PSScriptRoot
Set-Location $kok
foreach ($ad in 'DATABASE_URL', 'MUVEKKIL_ANAHTARI', 'AVUKAT_PG_SUPERPW', 'YEDEK_KLASORU') {
    $deger = [Environment]::GetEnvironmentVariable($ad, 'User')
    if ($deger) { Set-Item "env:$ad" $deger }
}

$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
& "$pgBin\pg_isready.exe" -h localhost -p 5432 -q
$biz_actik = $LASTEXITCODE -ne 0
if ($biz_actik) { & "$kok\db\db-baslat.ps1" | Out-Null }

try {
    & "$kok\.venv\Scripts\python.exe" -m app.yedek otomatik --sakla $Sakla
    $cikis = $LASTEXITCODE
} finally {
    if ($biz_actik) { & "$kok\db\db-baslat.ps1" -Durdur | Out-Null }
}
exit $cikis
