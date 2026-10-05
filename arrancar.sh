#!/usr/bin/env bash
# Arranca el servicio de IA y el backend en dos terminales separados.
# Requisitos: PostgreSQL en marcha y haber hecho la instalación una vez (ver README.md).
# Uso (desde la carpeta del proyecto):
#   chmod +x arrancar.sh
#   ./arrancar.sh

ROOT="$(cd "$(dirname "$0")" && pwd)"

open_term() {
  local title="$1"
  local cmd="$2"

  if command -v foot >/dev/null 2>&1; then
    foot --title "$title" bash -lc "$cmd; if command -v fish >/dev/null 2>&1; then exec fish; else exec bash; fi" &
    return
  fi

  if command -v alacritty >/dev/null 2>&1; then
    alacritty --title "$title" -e bash -lc "$cmd; if command -v fish >/dev/null 2>&1; then exec fish; else exec bash; fi" &
    return
  fi

  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title "$title" -- bash -lc "$cmd; if command -v fish >/dev/null 2>&1; then exec fish; else exec bash; fi" &
    return
  fi

  if command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -e "bash -lc '$cmd; if command -v fish >/dev/null 2>&1; then exec fish; else exec bash; fi'" &
    return
  fi

  if command -v konsole >/dev/null 2>&1; then
    konsole --hold -e bash -lc "$cmd; if command -v fish >/dev/null 2>&1; then exec fish; else exec bash; fi" &
    return
  fi

  if command -v xfce4-terminal >/dev/null 2>&1; then
    xfce4-terminal --hold -e "bash -lc '$cmd; if command -v fish >/dev/null 2>&1; then exec fish; else exec bash; fi'" &
    return
  fi

  echo "No encontré un terminal compatible. Ejecuta estas dos cosas manualmente:" >&2
  echo "  cd '$ROOT/ai-service'; python3 -m venv .venv; . .venv/bin/activate; python -m pip install -r requirements.txt; [ -f .env ] || cp .env.example .env; python -m app.data.seed; python -m uvicorn app.main:app --port 8001" >&2
  echo "  cd '$ROOT/backend'; chmod +x mvnw; ./mvnw spring-boot:run" >&2
  exit 1
}

AI_CMD="cd \"$ROOT/ai-service\"; if [ ! -d .venv ]; then python3 -m venv .venv; fi; . .venv/bin/activate; python -m pip install --upgrade pip >/dev/null 2>&1; python -m pip install -r requirements.txt >/dev/null 2>&1; [ -f .env ] || cp .env.example .env; python -m app.data.seed >/dev/null 2>&1 || true; python -m uvicorn app.main:app --port 8001"
BACKEND_CMD="cd \"$ROOT/backend\"; chmod +x mvnw; ./mvnw spring-boot:run"

open_term "Dona IA" "$AI_CMD"
open_term "Dona Backend" "$BACKEND_CMD"

echo "Servicio de IA:  http://localhost:8001/docs"
echo "App de Dona:     http://localhost:8080   (plan B solo con IA: http://localhost:8001)"
