"""Trazas visuales en la consola del servicio de IA: qué pasa por dentro cada vez que la app hace algo.

Cada petición se imprime como un bloque (cabecera, pasos y pie con el tiempo). Los pasos se acumulan y el
bloque se imprime entero al terminar, para que las peticiones simultáneas de la app no se mezclen.

    +--------------------------------------------------------------------------+
    | POST   /api/clientes/C0001/chat                                 12:16:03 |
    +--------------------------------------------------------------------------+
      APP     --->  DONA         "30 € para una persona celíaca y dos veganas"
      DONA    --->  LLM          Preguntando a ollama (qwen2.5:7b)...
      LLM     --->  DONA         Decide usar: preparar_cesta(presupuesto=30, personas=3, ...)
      DONA    --->  POSTGRES     Historial: 139 compras · gustos: Desayunos, Fitness
      CESTA                      12 productos · 29,67 € de 30 € · apta: sin gluten, vegano
      <== 200 OK                 [###.................] 160 ms

Colores ANSI; se desactivan con TRAZAS_COLOR=0 en .env. Sin trazas: TRAZAS=0.
"""
from __future__ import annotations

import contextvars
import os
import threading
from datetime import datetime

ACTIVAS = os.getenv("TRAZAS", "1") != "0"
COLOR = os.getenv("TRAZAS_COLOR", "1") != "0"
if COLOR and os.name == "nt":
    os.system("")  # activa los códigos de color en la consola de Windows

ANCHO = 78
_R, _B = "\033[0m", "\033[1m"
COLORES = {"verde": "\033[32m", "amarillo": "\033[33m", "azul": "\033[34m", "magenta": "\033[35m",
           "cian": "\033[36m", "rojo": "\033[31m", "gris": "\033[90m"}

# etiqueta -> (texto de la flecha, color)
FLUJO = {
    "APP": ("APP     --->  DONA", "verde"),
    "BD": ("DONA    --->  POSTGRES", "azul"),
    "LLM": ("DONA    --->  LLM", "magenta"),
    "LLM_OK": ("LLM     --->  DONA", "magenta"),
    "LLM_FALLO": ("LLM     -X->  DONA", "rojo"),
    "HERRAMIENTA": ("DONA    ===>  HERRAMIENTA", "cian"),
    "MODELO": ("RECOMENDADOR (PyTorch)", "magenta"),
    "RESULTADO": ("RESULTADO", "verde"),
    "CESTA": ("CESTA", "amarillo"),
    "TICKET": ("#  TICKET DIGITAL", "verde"),
    "DEDUPLICADO": ("=  DEDUPLICADO", "amarillo"),
    "GUARDADO": ("DONA    --->  POSTGRES", "azul"),
    "GUSTOS": ("GUSTOS APRENDIDOS", "amarillo"),
    "RESPUESTA": ("DONA    --->  APP", "verde"),
    "ERROR": ("!! ERROR", "rojo"),
}

_bloque: contextvars.ContextVar[list | None] = contextvars.ContextVar("traza_bloque", default=None)
_lock = threading.Lock()


def _c(color: str, texto: str, negrita: bool = False) -> str:
    if not COLOR:
        return texto
    return (_B if negrita else "") + COLORES.get(color, "") + texto + _R


def _ajustar(texto: str, ancho: int) -> str:
    return texto[: ancho - 3] + "..." if len(texto) > ancho else texto.ljust(ancho)


def paso(etiqueta: str, mensaje: str) -> None:
    """Un paso de lo que está pasando. Dentro de una petición se acumula; fuera, se imprime directamente."""
    if not ACTIVAS:
        return
    flecha, color = FLUJO.get(etiqueta, ("*  " + etiqueta, "amarillo"))
    linea = "  " + _c(color, _ajustar(flecha, 26), negrita=etiqueta == "ERROR") + " " + mensaje
    bloque = _bloque.get()
    if bloque is None:
        with _lock:
            print(linea, flush=True)
    else:
        bloque.append(linea)


def empezar() -> contextvars.Token:
    return _bloque.set([])


def terminar(token: contextvars.Token, metodo: str, ruta: str, estado: int, ms: int) -> None:
    lineas = _bloque.get() or []
    _bloque.reset(token)
    if not ACTIVAS:
        return
    borde = _c("gris", "+" + "-" * (ANCHO - 2) + "+")
    hora = datetime.now().strftime("%H:%M:%S")
    cab = (_c("gris", "| ") + _c("verde", _ajustar(metodo, 7), True) + _c("", _ajustar(ruta, ANCHO - 4 - 7 - 8), True)
           + _c("gris", hora + " |"))
    ok = estado < 400
    bloques = min(20, max(1, ms // 50))
    barra = "[" + "#" * bloques + "." * (20 - bloques) + "]"
    texto = {200: "OK", 201: "Creado", 400: "Petición incorrecta", 404: "No encontrado", 422: "Datos no válidos",
             500: "Error interno", 503: "Sin LLM disponible"}.get(estado, "")
    pie = ("  " + _c("verde" if ok else "rojo", _ajustar(("<== " if ok else "<!! ") + f"{estado} {texto}", 26), True)
           + " " + _c("verde" if ok else "rojo", barra) + f" {ms} ms")
    with _lock:
        print("\n" + "\n".join([borde, cab, borde, *lineas, pie]), flush=True)


def recortar(texto: str, n: int = 90) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= n else texto[: n - 1] + "…"
