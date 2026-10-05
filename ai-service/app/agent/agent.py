"""Agente con tool-calling, memoria por sesión y traza visible (para enseñar al jurado qué hace).

Añadir una herramienta nueva el día D (5 minutos):

    @registry.tool("nombre_tool", "Qué hace y cuándo usarla", {
        "type": "object",
        "properties": {"param": {"type": "string", "description": "..."}},
        "required": ["param"],
    })
    def nombre_tool(ctx: ToolContext, param: str) -> dict:
        return {...}            # siempre algo serializable a JSON
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config import settings
from app.llm.gateway import LLMGateway


@dataclass
class ToolContext:
    session_id: str
    extra: dict = field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}

    def tool(self, name: str, description: str, parameters: dict) -> Callable:
        def deco(fn: Callable) -> Callable:
            self._tools[name] = {"fn": fn, "spec": {"name": name, "description": description, "parameters": parameters}}
            return fn
        return deco

    def specs(self, only: list[str] | None = None) -> list[dict]:
        return [t["spec"] for n, t in self._tools.items() if only is None or n in only]

    def call(self, name: str, args: dict, ctx: ToolContext) -> Any:
        if name not in self._tools:
            return {"error": f"Herramienta desconocida: {name}"}
        try:
            return self._tools[name]["fn"](ctx, **args)
        except TypeError as e:
            return {"error": f"Argumentos no válidos para {name}: {e}"}
        except Exception as e:  # la herramienta falla -> el agente lo ve y puede reintentar/explicar
            return {"error": f"{type(e).__name__}: {e}"}


class Agent:
    def __init__(self, gateway: LLMGateway, registry: ToolRegistry, system_prompt: str | Callable[[str], str], max_steps: int = 6,
                 history_limit: int = 24) -> None:
        self.gw, self.registry, self.system, self.max_steps = gateway, registry, system_prompt, max_steps
        self.history_limit = history_limit
        self.sessions: dict[str, list[dict]] = {}

    def reset(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def _trim(self, msgs: list[dict]) -> list[dict]:
        """Recorta historial sin dejar mensajes 'tool' huérfanos al principio."""
        if len(msgs) <= self.history_limit:
            return msgs
        cut = msgs[-self.history_limit:]
        while cut and cut[0]["role"] != "user":  # Anthropic exige empezar por 'user' y sin 'tool' huérfanos
            cut = cut[1:]
        return cut

    def run(self, session_id: str, user_message: str, images: list[dict] | None = None) -> dict:
        msgs = self.sessions.setdefault(session_id, [])
        content: Any = user_message
        if images:
            content = [*images, {"type": "text", "text": user_message}]
        msgs.append({"role": "user", "content": content})
        trace, t0, ctx = [], time.perf_counter(), ToolContext(session_id)
        providers = set()
        system = self.system(session_id) if callable(self.system) else self.system  # contexto del cliente

        for step in range(self.max_steps):
            resp = self.gw.complete(self._trim(msgs), tools=self.registry.specs(), system=system)
            providers.add(resp.provider)
            if not resp.tool_calls:
                msgs.append({"role": "assistant", "content": resp.text})
                trace.append({"tipo": "respuesta", "proveedor": resp.provider, "cache": resp.cached})
                break
            msgs.append({"role": "assistant", "content": resp.text,
                         "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in resp.tool_calls]})
            if resp.text:
                trace.append({"tipo": "pensamiento", "texto": resp.text})
            for tc in resp.tool_calls:
                ts = time.perf_counter()
                result = self.registry.call(tc.name, tc.arguments, ctx)
                trace.append({"tipo": "herramienta", "nombre": tc.name, "argumentos": tc.arguments,
                              "resultado_resumen": _summary(result), "ms": int((time.perf_counter() - ts) * 1000),
                              "proveedor": resp.provider, "tarjetas": _cards(result),
                              "cesta": result.get("cesta") if isinstance(result, dict) else None})
                msgs.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name,
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:settings.tool_result_max_chars]})
        else:
            msgs.append({"role": "assistant", "content": "He llegado al límite de pasos. ¿Puedes concretar un poco más?"})

        return {"respuesta": msgs[-1]["content"], "traza": trace, "proveedores": sorted(providers),
                "ms_total": int((time.perf_counter() - t0) * 1000)}


def _cards(result: Any) -> list[dict]:
    """Productos a mostrar como tarjetas en el chat (para que la UI no dependa del texto del LLM)."""
    if not isinstance(result, dict):
        return []
    items = result.get("productos") or result.get("recomendaciones") or []
    keep = ("id", "nombre", "marca", "precio", "seccion", "etiquetas", "alergenos", "motivo", "no_apto")
    return [{k: it[k] for k in keep if k in it} for it in items[:6]]


def _summary(result: Any) -> str:
    if isinstance(result, dict):
        if "error" in result:
            return f"error: {result['error']}"
        for key in ("productos", "seleccion", "recomendaciones", "items", "fuentes", "prevision"):
            if key in result and isinstance(result[key], list):
                return f"{len(result[key])} {key}"
        return ", ".join(list(result.keys())[:5])
    if isinstance(result, list):
        return f"{len(result)} elementos"
    return str(result)[:80]
