# Lance l'app Pinterest Finder
Set-Location $PSScriptRoot

if (-not (Test-Path "venv")) {
    Write-Host "-> Creation de l'environnement virtuel..." -ForegroundColor Cyan
    python -m venv venv
}

Write-Host "-> Installation des dependances..." -ForegroundColor Cyan
& "venv\Scripts\pip.exe" install -r requirements.txt -q

Write-Host "-> Demarrage sur http://localhost:5000" -ForegroundColor Green
& "venv\Scripts\python.exe" app.py
