# Günlük otomatik yedek için Windows Görev Zamanlayıcı görevini ekler ya da kaldırır.
#   .\calistir\yedek-gorevi.ps1               # ekle / güncelle (her gün 18:30)
#   .\calistir\yedek-gorevi.ps1 -Saat 12:30   # başka saat
#   .\calistir\yedek-gorevi.ps1 -Kaldir       # kaldır
#
# Görev yalnızca bu kullanıcı hesabında ve oturum açıkken çalışır: Windows parolası saklanmaz,
# yönetici yetkisi gerekmez. Bilgisayar o saatte kapalıysa kaçırılan yedek, oturum açıldığında alınır.

param([string]$Saat = '18:30', [switch]$Kaldir)

$ad = 'AvukatDosyaTakip Yedek'
if ($Kaldir) {
    Unregister-ScheduledTask -TaskName $ad -Confirm:$false
    "Görev kaldırıldı: $ad"
    exit
}

$betik = Join-Path $PSScriptRoot 'yedek.ps1'
$eylem = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$betik`""
$tetik = New-ScheduledTaskTrigger -Daily -At $Saat
$ayar = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$kim = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $ad -Action $eylem -Trigger $tetik -Settings $ayar -Principal $kim `
    -Description 'Avukat Dosya Takip: günlük şifreli yedek + tam doğrulama (calistir\yedek.ps1)' -Force | Out-Null
"Görev eklendi: $ad, her gün $Saat"
