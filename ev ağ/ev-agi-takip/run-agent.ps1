# Ev ağı agent — boşluklu yol için güvenli çalıştırma
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "UYARI: PowerShell Yönetici degil. Scapy tarama/sniff calismayabilir." -ForegroundColor Yellow
    Write-Host "Baslat menusu -> Windows PowerShell -> Sag tik -> Yonetici olarak calistir`n"
}

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$requirements = Join-Path $ProjectRoot "requirements.txt"
if (-not (Test-Path $venvPython)) {
    Write-Host "Sanal ortam olusturuluyor..."
    python -m venv (Join-Path $ProjectRoot ".venv")
}
$reqOk = & $venvPython -c "import requests" 2>$null
if (-not $reqOk) {
    & $venvPython -m pip install -q -r $requirements
}

$env:EV_AGI_SERVER = if ($env:EV_AGI_SERVER) { $env:EV_AGI_SERVER } else { "http://127.0.0.1:5000" }

$serverOk = $false
try {
    $null = Invoke-WebRequest -Uri "$($env:EV_AGI_SERVER)/login" -TimeoutSec 4 -UseBasicParsing
    $serverOk = $true
} catch { }

if (-not $serverOk) {
    Write-Host ""
    Write-Host "HATA: Flask sunucu calismiyor ($($env:EV_AGI_SERVER))" -ForegroundColor Red
    Write-Host "Once BASKA bir terminalde:  .\run-server.ps1" -ForegroundColor Yellow
    Write-Host "Sunucu acik kalsin; sonra bu pencerede tekrar .\run-agent.ps1" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

$modemEnv = Join-Path $ProjectRoot "modem.env"
if (Test-Path $modemEnv) {
    Get-Content $modemEnv | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $val = $matches[2].Trim()
            Set-Item -Path "env:$name" -Value $val
        }
    }
    Write-Host "modem.env yuklendi." -ForegroundColor Cyan
}

$env:PYTHONIOENCODING = "utf-8"
& $venvPython (Join-Path $ProjectRoot "agent\agent_main.py") @args
