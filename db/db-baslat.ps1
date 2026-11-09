# Yerel geliştirme veritabanını (PostgreSQL 18) başlatır.
# Sunucu Windows servisi olarak kurulu değildir; bilgisayar yeniden başladıktan sonra bu betik çalıştırılır.
# Durdurmak için: .\db\db-baslat.ps1 -Durdur
#
# Veri kökü %USERPROFILE%\AvukatDosyaTakipVeri (AVUKAT_VERI_KOKU ile değiştirilebilir); app/ayarlar.py
# veri_koku() ile aynıdır. AppData bilerek kullanılmaz: paketli uygulamaların AppData yazmaları sanal
# klasöre yönlendirilir ve dışarıdan (Görev Zamanlayıcı, kendi terminaliniz) görünmez.

param([switch]$Durdur)

$bin = 'C:\Program Files\PostgreSQL\18\bin'
$kok = [Environment]::GetEnvironmentVariable('AVUKAT_VERI_KOKU', 'User')
if (-not $kok) { $kok = "$env:USERPROFILE\AvukatDosyaTakipVeri" }

if ($Durdur) {
    & "$bin\pg_ctl.exe" -D "$kok\pgdata" -w stop
} else {
    & "$bin\pg_ctl.exe" -D "$kok\pgdata" -l "$kok\postgres.log" -w start
    & "$bin\pg_isready.exe" -h localhost -p 5432
}
