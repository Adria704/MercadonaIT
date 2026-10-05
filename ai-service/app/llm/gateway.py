"""Gateway LLM multi-proveedor.

Una sola interfaz para Ollama (Qwen 2.5 7B en local), Gemini y Groq (APIs gratuitas), con:
  * fallback automático en el orden de LLM_PROVIDERS (se salta los que no tienen clave),
  * reintentos con backoff y timeout,
  * tool-calling nativo con un formato canónico común,
  * imágenes (visión) en el mismo formato para todos,
  * salida estructurada validada con Pydantic (complete_json),
  * caché en disco: en modo "live" graba todo; en modo "replay" la demo funciona SIN red,
  * proveedor "mock" determinista para que la demo nunca se caiga,
  * estadísticas de tokens y latencia (endpoint /api/stats).

Formato canónico de mensajes (estilo OpenAI, independiente del proveedor):
  {"role": "user", "content": "texto"}
  {"role": "user", "content": [{"type": "text", "text": "..."},
                               {"type": "image", "media_type": "image/jpeg", "data": "<base64>"}]}
  {"role": "assistant", "content": "texto", "tool_calls": [{"id": "...", "name": "...", "arguments": {...}}]}
  {"role": "tool", "tool_call_id": "...", "name": "...", "content": "<json str>"}
Tools: [{"name": ..., "description": ..., "parameters": <JSON schema>}]
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app import trazas
from app.config import settings

log = logging.getLogger("llm.gateway")


# --------------------------------------------------------------------------- tipos
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    cached: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LLMResponse":
        d = dict(d)
        d["tool_calls"] = [ToolCall(**tc) for tc in d.get("tool_calls", [])]
        return cls(**d)


class ProviderError(Exception):
    pass


# --------------------------------------------------------------------------- utilidades
def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")
    return str(content or "")


def _extract_json(text: str) -> Any:
    """Extrae el primer objeto/array JSON de un texto (tolera ```json ...```)."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("No se encontró JSON válido en la respuesta")


# --------------------------------------------------------------------------- proveedores
class BaseProvider:
    name = "base"
    model = ""

    def available(self) -> bool:
        return True

    def complete(self, messages: list[dict], tools: list[dict] | None, system: str | None,
                 max_tokens: int, temperature: float) -> LLMResponse:
        raise NotImplementedError


class OpenAICompatProvider(BaseProvider):
    """Sirve para OpenAI, Gemini (endpoint compatible) y Ollama."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str, needs_key: bool = True):
        self.name, self.base_url, self.api_key, self.model = name, base_url.rstrip("/"), api_key, model
        self.needs_key = needs_key
        self._alive: bool | None = None

    def available(self) -> bool:
        if self.needs_key:
            return bool(self.api_key)
        if self._alive is None:  # Ollama: comprobamos una vez si está levantado
            try:
                httpx.get(f"{self.base_url}/models", timeout=1.5)
                self._alive = True
            except Exception:
                self._alive = False
        return self._alive

    @staticmethod
    def _convert(messages: list[dict], system: str | None) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            role = m["role"]
            if role == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
            elif role == "assistant":
                msg: dict = {"role": "assistant", "content": _text_of(m.get("content")) or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                        for tc in m["tool_calls"]
                    ]
                out.append(msg)
            else:
                content = m.get("content")
                if isinstance(content, list):
                    parts = []
                    for p in content:
                        if p["type"] == "text":
                            parts.append({"type": "text", "text": p["text"]})
                        elif p["type"] == "image":
                            parts.append({"type": "image_url",
                                          "image_url": {"url": f"data:{p['media_type']};base64,{p['data']}"}})
                    out.append({"role": role, "content": parts})
                else:
                    out.append({"role": role, "content": content})
        return out

    def complete(self, messages, tools, system, max_tokens, temperature) -> LLMResponse:
        body: dict = {
            "model": self.model,
            "messages": self._convert(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=settings.timeout)
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} {r.status_code}: {r.text[:300]}")
        data = r.json()
        msg = data["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed = {}
            calls.append(ToolCall(id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}", name=tc["function"]["name"], arguments=parsed))
        usage = data.get("usage") or {}
        return LLMResponse(text=msg.get("content") or "", tool_calls=calls, provider=self.name, model=self.model,
                           usage={"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)})


class OllamaProvider(BaseProvider):
    """Ollama con su API nativa (/api/chat): permite fijar num_ctx (el endpoint compatible con OpenAI no),
    imprescindible para que las herramientas y el historial no se trunquen en silencio."""

    name = "ollama"

    def __init__(self, url: str, model: str, num_ctx: int):
        self.url, self.model, self.num_ctx = url.rstrip("/"), model, num_ctx
        self._checked_at, self._ok = 0.0, False

    def available(self) -> bool:
        if time.time() - self._checked_at > 30:  # reintenta cada 30 s por si arrancas Ollama después
            self._checked_at = time.time()
            try:
                tags = httpx.get(f"{self.url}/api/tags", timeout=1.5).json()
                names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
                self._ok = self.model in names or f"{self.model}:latest" in names
                if not self._ok:
                    log.warning("Ollama está levantado pero falta el modelo. Ejecuta: ollama pull %s", self.model)
            except Exception:
                self._ok = False
        return self._ok

    @staticmethod
    def _convert(messages: list[dict], system: str | None) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}] if system else []
        for m in messages:
            role = m["role"]
            if role == "tool":
                out.append({"role": "tool", "content": m["content"], "tool_name": m.get("name", "")})
            elif role == "assistant":
                msg: dict = {"role": "assistant", "content": _text_of(m.get("content"))}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"function": {"name": tc["name"], "arguments": tc["arguments"]}} for tc in m["tool_calls"]]
                out.append(msg)
            else:
                content = m.get("content")
                if isinstance(content, list):
                    out.append({"role": role, "content": _text_of(content),
                                "images": [p["data"] for p in content if p["type"] == "image"]})
                else:
                    out.append({"role": role, "content": content})
        return out

    def complete(self, messages, tools, system, max_tokens, temperature) -> LLMResponse:
        body: dict = {"model": self.model, "messages": self._convert(messages, system), "stream": False,
                      "keep_alive": "30m",
                      "options": {"num_ctx": self.num_ctx, "temperature": temperature, "num_predict": max_tokens}}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        r = httpx.post(f"{self.url}/api/chat", json=body, timeout=settings.timeout)
        if r.status_code >= 400:
            raise ProviderError(f"ollama {r.status_code}: {r.text[:300]}")
        data = r.json()
        msg = data.get("message", {})
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=fn.get("name", ""), arguments=args))
        content = msg.get("content") or ""
        if tools and not calls:
            calls, content = self._tool_call_en_texto(content, {t["name"] for t in tools})
        return LLMResponse(text=content, tool_calls=calls, provider=self.name, model=self.model,
                           usage={"input_tokens": data.get("prompt_eval_count", 0), "output_tokens": data.get("eval_count", 0)})

    @staticmethod
    def _tool_call_en_texto(content: str, nombres: set[str]) -> tuple[list[ToolCall], str]:
        """Los modelos pequeños a veces escriben la llamada como texto: <tool_call>{...}</tool_call> o {"name":..}."""
        m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", content, re.S) or re.search(r"(\{\s*\"name\".*\})", content, re.S)
        if not m:
            return [], content
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            return [], content
        name = obj.get("name")
        args = obj.get("arguments") or obj.get("parameters") or {}
        if name not in nombres or not isinstance(args, dict):
            return [], content
        return [ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, arguments=args)], ""


class MockProvider(BaseProvider):
    """Respuestas deterministas sin red. Mantiene viva la demo si todo lo demás falla.

    Con tools: elige una herramienta por palabras clave y luego resume su resultado.
    Sin tools: devuelve un texto marcado como [modo demo].
    Personaliza KEYWORD_TOOLS el día D para que la demo offline cuente vuestra historia.
    """

    name = "mock"
    model = "mock-1"

    KEYWORD_TOOLS = [
        (("€", "euro", "pavos", "presupuesto"), "preparar_cesta"),
        (("recicl", "contenedor", "dónde tiro", "donde tiro", "tirar"), "reciclaje"),
        (("no me gusta", "odio", "me encanta", "me gusta"), "actualizar_gustos"),
        (("última vez", "ultima vez", "cuándo compré", "cuando compre", "cada cuánto", "cada cuanto"), "historial_producto"),
        (("ticket",), "ultimos_tickets"),
        (("gast", "cuánto llevo", "cuanto llevo"), "resumen_compras"),
        (("recomi", "suger", "qué compro", "que compro", "descubr", "nuevo", "para mí", "para mi"), "recomendaciones"),
    ]
    STOP = {"quiero", "busco", "necesito", "dame", "unos", "unas", "algún", "algun", "para", "con", "sin", "de", "la",
            "el", "los", "las", "un", "una", "me", "y", "que", "por", "favor", "hola", "puedes", "algo", "a", "en",
            "añade", "anade", "agrega", "mete", "pon", "carrito", "cesta", "al", "mi", "tengo", "hay", "cosas"}

    def complete(self, messages, tools, system, max_tokens, temperature) -> LLMResponse:
        last = messages[-1] if messages else {"role": "user", "content": ""}
        tool_names = {t["name"] for t in (tools or [])}

        last_user = next((_text_of(m.get("content")).lower() for m in reversed(messages) if m["role"] == "user"), "")
        wants_add = any(k in last_user for k in ("añad", "anad", "agrega", "mete", "pon "))

        if tools and last["role"] == "user":
            text = last_user
            chosen, args = None, {}
            if not wants_add:
                for keys, tool in self.KEYWORD_TOOLS:
                    if tool in tool_names and any(k in text for k in keys):
                        chosen = tool
                        break
            words = [w for w in re.findall(r"\w+", text) if w not in self.STOP and len(w) > 2]
            if chosen == "historial_producto":
                args = {"producto": " ".join(w for w in words if w not in ("ultima", "última", "vez", "compre", "compré", "cuando", "cuándo", "cada"))[:60]}
            elif chosen == "actualizar_gustos":
                neg = any(k in text for k in ("no me gusta", "odio"))
                obj = re.sub(r".*(no me gusta|odio|me encanta|me gusta)\s*(el|la|los|las)?\s*", "", text).strip(" .?!")
                args = {"no_me_gusta": [obj]} if neg else {"me_gusta": [obj]}
            elif chosen == "reciclaje":
                obj = re.sub(r".*(tiro|tirar|recicl\w*|contenedor)\s*(el|la|los|las|de)?\s*", "", text).strip(" .?!")
                args = {"producto": obj} if obj and len(obj) > 2 else {}
            elif chosen == "recomendaciones":
                args = {"tipo": "descubre" if ("descubr" in text or "nuevo" in text) else "para_ti"}
            elif chosen == "resumen_compras":
                args = {"periodo": "año" if "año" in text else "mes"}
            elif chosen == "preparar_cesta":
                args = self._pedido(text)
            elif chosen is None and "buscar_productos" in tool_names:
                words = [w for w in re.findall(r"\w+", text) if w not in self.STOP and len(w) > 2]
                chosen, args = "buscar_productos", {"consulta": " ".join(words[:4]) or text}
            if chosen:
                return LLMResponse(tool_calls=[ToolCall(id=f"mock_{uuid.uuid4().hex[:8]}", name=chosen, arguments=args)],
                                   provider=self.name, model=self.model)

        if last["role"] == "tool":
            try:
                data = json.loads(last["content"])
            except Exception:
                data = last["content"]
            # Demo offline: "añade X al carrito" -> buscar -> añadir el primero
            if (wants_add and last.get("name") == "buscar_productos" and "anadir_al_carrito" in tool_names
                    and isinstance(data, dict) and data.get("productos")):
                return LLMResponse(tool_calls=[ToolCall(id=f"mock_{uuid.uuid4().hex[:8]}", name="anadir_al_carrito",
                                                        arguments={"producto_id": data["productos"][0]["id"], "cantidad": 1})],
                                   provider=self.name, model=self.model)
            return LLMResponse(text=self._summarize(last.get("name", ""), data), provider=self.name, model=self.model)

        return LLMResponse(text="[modo demo] " + _text_of(last.get("content"))[:300], provider=self.name, model=self.model)

    NUM = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8}

    @classmethod
    def _pedido(cls, t: str) -> dict:
        """Extrae presupuesto, personas y dietas de una frase (solo para el modo sin LLM)."""
        args: dict = {}
        m = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur\b|pavos)", t)
        if m:
            args["presupuesto"] = float(m.group(1).replace(",", "."))
        restr, alerg = [], []
        if re.search(r"cel[ií]ac|gluten", t):
            restr.append("sin_gluten")
        if "vegan" in t:
            restr.append("vegano")
        if "vegetarian" in t:
            restr.append("vegetariano")
        if "lactosa" in t:
            alerg.append("lactosa")
        if "frutos secos" in t:
            alerg.append("frutos_secos")
        w = r"\d+|" + "|".join(cls.NUM)
        total = sum(int(x) if x.isdigit() else cls.NUM[x] for x in re.findall(
            rf"\b({w})\s+(?:personas?|adultos?|niñ[oa]s?|cel[ií]ac\w*|vegan\w*|vegetarian\w*|amig\w+)", t))
        if not total:
            m = re.search(rf"para\s+({w})\b", t)
            total = (int(m.group(1)) if m.group(1).isdigit() else cls.NUM[m.group(1)]) if m else 0
        if not total and re.search(r"para m[ií]\b|yo sol", t):
            total = 1
        if total:
            args["personas"] = total
        if restr:
            args["restricciones"] = restr
        if alerg:
            args["alergias"] = alerg
        return args

    @staticmethod
    def _summarize(tool: str, data: Any) -> str:
        head = "[modo demo sin LLM] "
        if isinstance(data, dict) and data.get("error"):
            return head + f"No he podido completar la acción: {data['error']}"
        if isinstance(data, dict) and "cesta" in data:
            c = data["cesta"]
            return head + (f"Te he preparado una cesta de {len(c['lineas'])} productos para {c['personas']} por "
                           f"{c['total']:.2f} € (te sobran {c['sobra']:.2f} €).")
        if isinstance(data, dict) and "recomendaciones" in data:
            lines = [f"• {r['nombre']} – {r.get('motivo', '')}" for r in data["recomendaciones"][:5]]
            return head + "Te recomiendo:\n" + "\n".join(lines)
        if isinstance(data, dict) and "veces" in data and "producto" in data:
            if not data["veces"]:
                return head + f"No has comprado {data['producto']} en el último año."
            return head + (f"Has comprado {data['producto']} {data['veces']} veces; la última el {data['ultima_compra']}"
                           + (f", más o menos cada {data['cada_dias']} días." if data.get("cada_dias") else "."))
        if isinstance(data, dict) and "gasto_total" in data:
            secs = ", ".join(f"{s['seccion']} ({s['gasto']:.0f} €)" for s in data.get("por_seccion", [])[:3])
            return head + f"En {data['periodo']} llevas {data['gasto_total']:.2f} € en {data['tickets']} compras. Donde más: {secs}."
        if isinstance(data, dict) and "tickets" in data and isinstance(data["tickets"], list):
            t = data["tickets"][0] if data["tickets"] else None
            return head + (f"Tu última compra fue el {t['fecha']} ({t['total']:.2f} €, {len(t['lineas'])} productos)." if t else "No tienes tickets.")
        if isinstance(data, dict) and "contenedores" in data:
            parts = [f"{c['componente']} → {c['contenedor']}" for c in data["contenedores"]]
            return head + f"{data.get('producto', 'Tu compra')}: " + "; ".join(parts)
        if isinstance(data, dict) and "por_contenedor" in data:
            parts = [f"{k}: {v}" for k, v in data["por_contenedor"].items()]
            return head + "Envases de tu última compra por contenedor → " + ", ".join(parts)
        if isinstance(data, dict) and "actualizado" in data:
            return head + "Apuntado, tendré en cuenta tus gustos en las próximas recomendaciones."
        if isinstance(data, dict) and "productos" in data:
            items = data["productos"][:5]
            if not items:
                return head + "No he encontrado productos para esa búsqueda."
            lines = [f"• {p['nombre']} – {p['precio']:.2f} €" for p in items]
            return head + "Esto es lo que he encontrado:\n" + "\n".join(lines)
        if isinstance(data, dict) and "items" in data and "total" in data:
            lines = [f"• {i['cantidad']} × {i['nombre']}" for i in data["items"][:10]]
            return head + f"Tu carrito ({data['total']:.2f} €):\n" + ("\n".join(lines) or "está vacío")
        return head + json.dumps(data, ensure_ascii=False)[:600]


# --------------------------------------------------------------------------- gateway
class LLMGateway:
    def __init__(self) -> None:
        s = settings
        registry: dict[str, BaseProvider] = {
            "ollama": OllamaProvider(s.ollama_url, s.ollama_model, s.ollama_num_ctx),
            "gemini": OpenAICompatProvider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", s.gemini_key, s.gemini_model),
            "groq": OpenAICompatProvider("groq", "https://api.groq.com/openai/v1", s.groq_key, s.groq_model),
            "mock": MockProvider(),
        }
        self.providers = [registry[p] for p in s.providers if p in registry]
        self.mock = registry["mock"]
        self.stats: dict = {"calls": 0, "cache_hits": 0, "by_provider": {}, "errors": []}
        s.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- caché
    @staticmethod
    def _key(messages, tools, system, temperature) -> str:
        blob = json.dumps({"m": messages, "t": tools, "s": system, "temp": temperature}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _cache_get(self, key: str) -> LLMResponse | None:
        f = settings.cache_dir / f"{key}.json"
        if f.exists():
            resp = LLMResponse.from_dict(json.loads(f.read_text()))
            resp.cached = True
            self.stats["cache_hits"] += 1
            return resp
        return None

    @staticmethod
    def _cache_put(key: str, resp: LLMResponse) -> None:
        if resp.provider == "mock":
            return
        (settings.cache_dir / f"{key}.json").write_text(json.dumps(resp.to_dict(), ensure_ascii=False))

    def _record(self, resp: LLMResponse) -> None:
        self.stats["calls"] += 1
        p = self.stats["by_provider"].setdefault(resp.provider, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0})
        p["calls"] += 1
        p["input_tokens"] += resp.usage.get("input_tokens", 0)
        p["output_tokens"] += resp.usage.get("output_tokens", 0)
        p["latency_ms"] += resp.latency_ms

    def available_providers(self) -> list[str]:
        return [p.name for p in self.providers if p.available()]

    # ---- API pública
    def complete(self, messages: list[dict], tools: list[dict] | None = None, system: str | None = None,
                 max_tokens: int | None = None, temperature: float = 0.3) -> LLMResponse:
        max_tokens = max_tokens or settings.max_tokens
        key = self._key(messages, tools, system, temperature)

        if settings.llm_mode == "replay":
            resp = self._cache_get(key) or self.mock.complete(messages, tools, system, max_tokens, temperature)
            trazas.paso("LLM_OK", f"Respuesta grabada (modo replay, {resp.provider})")
            self._record(resp)
            return resp
        if settings.cache_read and (hit := self._cache_get(key)):
            trazas.paso("LLM_OK", f"Respuesta reutilizada de la caché ({hit.provider})")
            self._record(hit)
            return hit

        errors = []
        for prov in self.providers:
            if not prov.available():
                continue
            for attempt in range(2):
                t0 = time.perf_counter()
                try:
                    if prov.name == "mock":
                        trazas.paso("LLM", "Ningún modelo disponible: respondo en modo demo (sin IA generativa)")
                    else:
                        trazas.paso("LLM", f"Preguntando a {prov.name} ({prov.model})...")
                    resp = prov.complete(messages, tools, system, max_tokens, temperature)
                    resp.latency_ms = int((time.perf_counter() - t0) * 1000)
                    if prov.name != "mock":
                        tok = resp.usage.get("input_tokens", 0) + resp.usage.get("output_tokens", 0)
                        trazas.paso("LLM_OK", f"{prov.name} respondió en {resp.latency_ms} ms ({tok} tokens)")
                    self._cache_put(key, resp)
                    self._record(resp)
                    return resp
                except (ProviderError, httpx.HTTPError, KeyError, ValueError) as e:
                    msg = f"{prov.name} intento {attempt + 1}: {e}"
                    log.warning(msg)
                    trazas.paso("LLM_FALLO", trazas.recortar(f"{prov.name} ha fallado ({e}); pruebo de nuevo o con el siguiente", 100))
                    errors.append(msg)
                    time.sleep(0.6 * (attempt + 1))
        self.stats["errors"] = (self.stats["errors"] + errors)[-20:]
        raise RuntimeError("Todos los proveedores fallaron: " + " | ".join(errors[-4:]))

    def ask(self, prompt: str, system: str | None = None, **kw) -> str:
        return self.complete([{"role": "user", "content": prompt}], system=system, **kw).text

    def complete_json(self, messages: list[dict], schema: type[BaseModel] | None = None, system: str | None = None,
                      fallback: dict | None = None, **kw) -> dict:
        """Devuelve un dict validado. Si el modelo falla dos veces (o es mock), devuelve `fallback`."""
        schema_txt = json.dumps(schema.model_json_schema(), ensure_ascii=False) if schema else "un objeto JSON"
        sys = (system or "") + f"\n\nResponde ÚNICAMENTE con JSON válido (sin texto extra ni ```) que cumpla este esquema:\n{schema_txt}"
        msgs = list(messages)
        for _ in range(2):
            resp = self.complete(msgs, system=sys.strip(), temperature=0.1, **kw)
            if resp.provider == "mock" and fallback is not None:
                return {**fallback, "_proveedor": "mock"}
            try:
                data = _extract_json(resp.text)
                if schema:
                    data = schema.model_validate(data).model_dump()
                return {**data, "_proveedor": resp.provider} if isinstance(data, dict) else {"items": data}
            except (ValueError, ValidationError) as e:
                msgs = msgs + [{"role": "assistant", "content": resp.text},
                               {"role": "user", "content": f"El JSON no era válido ({e}). Devuélvelo corregido, solo JSON."}]
        if fallback is not None:
            return {**fallback, "_proveedor": "fallback"}
        raise ValueError("El modelo no devolvió JSON válido")


gateway = LLMGateway()
