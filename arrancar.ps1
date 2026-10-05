# Arranca el servicio de IA y el backend en dos ventanas de PowerShell.
# Requisitos: PostgreSQL en marcha y haber hecho la instalación una vez (ver README.md).
# Uso (desde la carpeta del proyecto):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\arrancar.ps1

$raiz = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd '$raiz\ai-service'
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --port 8001
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
cd '$raiz\backend'
.\mvnw.cmd spring-boot:run
"@

Write-Host "Servicio de IA:  http://localhost:8001/docs"
Write-Host "App de Dona:     http://localhost:8080   (plan B solo con IA: http://localhost:8001)"
