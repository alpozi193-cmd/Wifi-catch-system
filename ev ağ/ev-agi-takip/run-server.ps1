# Flask sunucu — boşluklu yol için güvenli çalıştırma
$ProjectRoot = $PSScriptRoot
Set-Location (Join-Path $ProjectRoot "server")

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$requirements = Join-Path $ProjectRoot "requirements.txt"

if (-not (Test-Path $venvPython)) {
    Write-Host "Sanal ortam olusturuluyor..."
    python -m venv (Join-Path $ProjectRoot ".venv")
}

$flaskOk = & $venvPython -c "import flask" 2>$null; if (-not $flaskOk) {
    Write-Host "Bagimliliklar yukleniyor (flask, sqlalchemy)..."
    & $venvPython -m pip install -q -r $requirements
}

# Ust klasordeki .venv'i kullanmayin — bu proje ev-agi-takip\.venv
& $venvPython app.py @args
