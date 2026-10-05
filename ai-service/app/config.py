"""Configuración del servicio de IA (variables de entorno / .env)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    """Variable de entorno; si no existe o está vacía en el .env, usa el valor por defecto."""
    return (os.getenv(name) or "").strip() or default


class Settings:
    def __init__(self) -> None:
        # Base de datos: SQLite por defecto (cero instalación). En el entorno real, PostgreSQL:
        #   DATABASE_URL=postgresql+psycopg://usuario:clave@localhost:5432/compras
        self.database_url = _env("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'compras.db').as_posix()}")

        # LLM: primero Qwen 2.5 7B en local (Ollama); si no está, API gratuita; "mock" como red de seguridad.
        self.providers = [p.strip() for p in _env("LLM_PROVIDERS", "ollama,gemini,groq,mock").split(",") if p.strip()]
        self.llm_mode = _env("LLM_MODE", "live").lower()
        self.cache_read = _env("LLM_CACHE_READ", "0") == "1"
        self.timeout = float(_env("LLM_TIMEOUT", "120"))
        self.max_tokens = int(_env("LLM_MAX_TOKENS", "1200"))

        self.ollama_url = _env("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model = _env("OLLAMA_MODEL", "qwen2.5:7b")
        self.ollama_num_ctx = int(_env("OLLAMA_NUM_CTX", "8192"))

        self.gemini_key = _env("GEMINI_API_KEY")
        self.gemini_model = _env("GEMINI_MODEL", "gemini-2.5-flash")
        self.groq_key = _env("GROQ_API_KEY")
        self.groq_model = _env("GROQ_MODEL", "llama-3.3-70b-versatile")

        hoy = _env("DEMO_HOY")
        self.demo_hoy = date.fromisoformat(hoy) if hoy else None

        self.models_dir = ROOT / "models"
        self.cache_dir = ROOT / ".cache" / "llm"
        self.tool_result_max_chars = int(_env("TOOL_RESULT_MAX_CHARS", "5000"))


settings = Settings()


def hoy() -> date:
    return settings.demo_hoy or date.today()
