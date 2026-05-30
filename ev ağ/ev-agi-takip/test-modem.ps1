# Modem baglanti testi (sunucu gerekmez)
$ProjectRoot = $PSScriptRoot
$modemEnv = Join-Path $ProjectRoot "modem.env"
if (Test-Path $modemEnv) {
    Get-Content $modemEnv | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
        }
    }
}
$env:EV_AGI_MODEM_DEBUG = "1"
$py = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Set-Location (Join-Path $ProjectRoot "agent")
& $py -c "from modem_client import fetch_modem_devices; d,m=fetch_modem_devices(); print('Sonuc:', len(d), 'cihaz, yontem=', m)"
