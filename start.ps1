# EduBot — Script de inicio con modelo LLM (SmolLM2)
# Activa el venv, instala dependencias y lanza la app con el modelo real.

Write-Host "=== EduBot — Iniciando con modelo LLM ===" -ForegroundColor Cyan

# Activar venv
& "$PSScriptRoot\venv\Scripts\Activate.ps1"

# Instalar dependencias (si ya están instaladas es rápido)
Write-Host "`nInstalando / verificando dependencias..." -ForegroundColor Yellow
pip install -r "$PSScriptRoot\requirements.txt"

# Lanzar app con LLM activado
Write-Host "`nCargando SmolLM2 y levantando servidor..." -ForegroundColor Green
Write-Host "La primera vez puede tardar varios minutos descargando el modelo (~750 MB)." -ForegroundColor DarkYellow
Write-Host "Abre http://127.0.0.1:5000 cuando veas ' * Running on http://127.0.0.1:5000'" -ForegroundColor Cyan

$env:EDUBOT_USE_LLM = "1"
python "$PSScriptRoot\app.py"
