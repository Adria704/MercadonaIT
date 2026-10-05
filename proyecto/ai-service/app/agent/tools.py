"""Herramientas del asistente personal + prompt de sistema con el contexto de cada cliente.

La sesión del agente es el id del cliente: cada herramienta trabaja sobre SUS datos.
Regla de diseño: el LLM orquesta y conversa; cifras, fechas y aptitud de productos se calculan en código.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.agent.agent import Agent, ToolContext, ToolRegistry
from app.cesta import cesta as cesta_mod
from app.config import hoy
from app.data import catalogo
from app.data.calendar_es import fecha_texto
from app.db import query_df
from app.llm.gateway import gateway
from app.perfil import perfil
from app.perfil.intereses import INTERESES, RESTRICCIONES
from app.recsys.recommender import recomendar
from app.reciclaje import reciclaje
from app.wrapped import wrapped

registry = ToolRegistry()


def _rango(periodo: str) -> tuple[date, date, str]:
    h = hoy()
    fin = h + timedelta(days=1)
    if periodo == "semana":
        return h - timedelta(days=6), fin, "los últimos 7 días"
    if periodo == "año":
        return date(h.year, 1, 1), fin, f"lo que va de {h.year}"
    if periodo == "30d":
        return h - timedelta(days=29), fin, "los últimos 30 días"
    return date(h.year, h.month, 1), fin, "lo que va de mes"


@registry.tool("buscar_productos", "Busca productos del catálogo. Cada producto indica en 'no_apto' si choca con las restricciones del cliente.", {
    "type": "object",
    "properties": {"consulta": {"type": "string", "description": "Texto libre: 'yogur', 'algo para cenar'..."},
                   "limite": {"type": "integer", "description": "Máximo de resultados (por defecto 6)"}},
    "required": ["consulta"],
})
def buscar_productos(ctx: ToolContext, consulta: str, limite: int = 6) -> dict:
    prefs = perfil.preferencias(ctx.session_id)
    out = []
    for p in catalogo.buscar(consulta, limite):
        motivos = perfil.no_apto(catalogo.df().loc[p["id"]], prefs)
        out.append({**p, "no_apto": motivos})
    return {"productos": out}


@registry.tool("resumen_compras", "Gasto y número de compras del cliente en un periodo, desglosado por sección.", {
    "type": "object",
    "properties": {"periodo": {"type": "string", "enum": ["semana", "mes", "30d", "año"]},
                   "seccion": {"type": "string", "description": "Opcional: filtra por sección (p. ej. 'Fruta y verdura')"}},
})
def resumen_compras(ctx: ToolContext, periodo: str = "mes", seccion: str | None = None) -> dict:
    d, h, etiqueta = _rango(periodo)
    df = query_df("""SELECT t.id AS ticket_id, l.cantidad, l.precio_unitario, p.seccion, p.sensible
                     FROM tickets t JOIN lineas_ticket l ON l.ticket_id = t.id JOIN productos p ON p.id = l.producto_id
                     WHERE t.cliente_id = :c AND t.fecha >= :d AND t.fecha < :h""", c=ctx.session_id, d=d, h=h)
    if seccion:
        df = df[df.seccion.str.lower().str.contains(seccion.lower())]
    df = df.assign(gasto=df.cantidad * df.precio_unitario)
    secs = df.groupby("seccion").gasto.sum().sort_values(ascending=False)
    return {"periodo": etiqueta, "tickets": int(df.ticket_id.nunique()), "gasto_total": round(float(df.gasto.sum()), 2),
            "por_seccion": [{"seccion": k, "gasto": round(float(v), 2)} for k, v in secs.head(6).items()]}


@registry.tool("historial_producto", "Cuántas veces y cada cuánto compra el cliente un producto, y cuándo fue la última vez.", {
    "type": "object", "properties": {"producto": {"type": "string"}}, "required": ["producto"]})
def historial_producto(ctx: ToolContext, producto: str) -> dict:
    p = catalogo.resolver(producto)
    if not p:
        return {"error": f"No encuentro '{producto}' en el catálogo"}
    clave = catalogo.df().loc[p["id"], "clave"]
    df = query_df("""SELECT t.fecha, l.cantidad, l.precio_unitario FROM tickets t JOIN lineas_ticket l ON l.ticket_id = t.id
                     JOIN productos p ON p.id = l.producto_id
                     WHERE t.cliente_id = :c AND p.clave = :k AND t.fecha >= :d ORDER BY t.fecha""",
                  c=ctx.session_id, k=clave, d=hoy() - timedelta(days=365))
    if df.empty:
        return {"producto": p["nombre"], "veces": 0}
    fechas = df.fecha.dt.normalize().drop_duplicates()
    cada = int(fechas.diff().dt.days.dropna().median()) if len(fechas) > 1 else None
    return {"producto": p["nombre"], "veces": int(len(fechas)), "unidades": int(df.cantidad.sum()),
            "ultima_compra": fecha_texto(fechas.iloc[-1].date()), "cada_dias": cada,
            "gasto_ultimo_año": round(float((df.cantidad * df.precio_unitario).sum()), 2)}


@registry.tool("ultimos_tickets", "Últimos tickets del cliente con sus productos.", {
    "type": "object", "properties": {"n": {"type": "integer", "description": "Cuántos (por defecto 3)"}}})
def ultimos_tickets(ctx: ToolContext, n: int = 3) -> dict:
    t = query_df("""SELECT id, fecha, total, metodo_pago FROM tickets WHERE cliente_id = :c ORDER BY fecha DESC LIMIT :n""",
                 c=ctx.session_id, n=min(int(n), 10))
    out = []
    for r in t.itertuples():
        lin = query_df("""SELECT p.nombre, l.cantidad FROM lineas_ticket l JOIN productos p ON p.id = l.producto_id
                          WHERE l.ticket_id = :t AND p.sensible = :f""", t=r.id, f=False)
        out.append({"id": r.id, "fecha": fecha_texto(r.fecha.date()), "total": float(r.total), "pago": r.metodo_pago,
                    "lineas": [f"{x.cantidad} × {x.nombre}" for x in lin.itertuples()]})
    return {"tickets": out}


@registry.tool("recomendaciones", "Recomendaciones personalizadas que se adaptan a gustos y compras, con su motivo.", {
    "type": "object",
    "properties": {"tipo": {"type": "string", "enum": ["para_ti", "descubre", "lo_de_siempre", "todas"],
                            "description": "para_ti = afines; descubre = cosas nuevas; lo_de_siempre = habituales"},
                   "n": {"type": "integer"}},
})
def recomendaciones(ctx: ToolContext, tipo: str = "para_ti", n: int = 5) -> dict:
    r = recomendar(ctx.session_id, max(int(n), 3))
    if tipo == "todas":
        lista = r["lo_de_siempre"][:2] + r["para_ti"][:3] + r["descubre"][:2]
    else:
        lista = r.get(tipo, r["para_ti"])[:n]
    keep = ("id", "nombre", "precio", "seccion", "motivo")
    return {"recomendaciones": [{k: x[k] for k in keep} for x in lista], "adaptacion": r["adaptacion"]["mensaje"]}


@registry.tool("actualizar_gustos", "Guarda lo que al cliente le gusta o no (productos, secciones o intereses). Úsala cuando lo diga.", {
    "type": "object",
    "properties": {"me_gusta": {"type": "array", "items": {"type": "string"}},
                   "no_me_gusta": {"type": "array", "items": {"type": "string"}}},
})
def actualizar_gustos(ctx: ToolContext, me_gusta: list[str] | None = None, no_me_gusta: list[str] | None = None) -> dict:
    return perfil.actualizar_gustos(ctx.session_id, me_gusta, no_me_gusta)


@registry.tool("mi_wrapped", "Resumen estilo Wrapped de las compras del cliente: producto obsesión, rachas, reciclaje...", {
    "type": "object",
    "properties": {"periodo": {"type": "string", "description": "'2026' (año), '2026-09' (mes) o vacío (último año)"}},
})
def mi_wrapped(ctx: ToolContext, periodo: str | None = None) -> dict:
    w = wrapped.generar(ctx.session_id, periodo or None, usar_llm=False)
    return {"titular": w["titular"], "tarjetas": w["tarjetas"]}


@registry.tool("reciclaje", "A qué contenedor va el envase de un producto; sin producto, resume la última compra.", {
    "type": "object", "properties": {"producto": {"type": "string"}}})
def reciclaje_tool(ctx: ToolContext, producto: str | None = None) -> dict:
    if producto:
        p = catalogo.resolver(producto)
        if not p:
            return {"error": f"No encuentro '{producto}'"}
        return reciclaje.donde_tiro({**p, "envase": catalogo.df().loc[p["id"], "envase"]})
    t = query_df("SELECT id FROM tickets WHERE cliente_id = :c ORDER BY fecha DESC LIMIT 1", c=ctx.session_id)
    if t.empty:
        return {"error": "Aún no tienes compras"}
    return reciclaje.resumen_ticket(t.id.iloc[0])


@registry.tool("preparar_cesta", "Llena una cesta de la compra ajustada a un presupuesto, nº de personas y dietas. "
               "Úsala siempre que el cliente pida una compra o cesta con un importe (p. ej. '30 € para dos, una celíaca').", {
    "type": "object",
    "properties": {
        "presupuesto": {"type": "number", "description": "Euros máximos"},
        "personas": {"type": "integer", "description": "Para cuántas personas (por defecto 2)"},
        "restricciones": {"type": "array", "items": {"type": "string", "enum": ["vegano", "vegetariano", "sin_gluten"]},
                          "description": "Dietas que debe cumplir TODA la cesta (celíaco = sin_gluten)"},
        "alergias": {"type": "array", "items": {"type": "string", "enum": ["gluten", "lactosa", "huevo", "pescado", "crustaceos", "frutos_secos", "sesamo"]}},
    },
    "required": ["presupuesto"],
})
def preparar_cesta(ctx: ToolContext, presupuesto: float, personas: int = 2, restricciones: list[str] | None = None,
                   alergias: list[str] | None = None) -> dict:
    return cesta_mod.preparar(ctx.session_id, presupuesto, personas, restricciones, alergias)


SYSTEM_BASE = """Eres Dona, la asistente personal de compra de un supermercado (lema: «Dona, no te abandona»). Hablas en español de España, cercano y breve (máximo 120 palabras).
Reglas:
- Usa SIEMPRE las herramientas para datos del cliente, productos, gasto o recomendaciones. Nunca inventes cifras, fechas ni productos.
- La aptitud de un producto la decide el campo 'no_apto' de las herramientas, nunca tu opinión. Si un producto no es apto, dilo claramente.
- Si el cliente expresa un gusto ("me encanta X", "no me gusta Y"), guárdalo con actualizar_gustos y confírmalo.
- Cuando recomiendes, explica el motivo en pocas palabras.
- Si te piden una compra con presupuesto, usa preparar_cesta y resume en una o dos frases (la app muestra el ticket).
- Los datos son de demostración (sintéticos)."""


def system_for(cliente_id: str) -> str:
    c = perfil.obtener(cliente_id)
    if not c:
        return SYSTEM_BASE + "\nEl cliente no está identificado."
    prefs = perfil.preferencias(cliente_id)
    gustos = ", ".join(INTERESES[i]["titulo"] for i in prefs["intereses"] if i in INTERESES) or "sin indicar"
    restr = ", ".join([RESTRICCIONES[r]["titulo"] for r in prefs["restricciones"]] + [f"alergia a {a}" for a in prefs["alergias"]]) or "ninguna"
    return (SYSTEM_BASE + f"\n\nCliente: {c['nombre']}. Hoy es {fecha_texto(hoy())} de {hoy().year}."
            f"\nGustos elegidos al crear la cuenta: {gustos}.\nRestricciones: {restr}.")


agent = Agent(gateway, registry, system_for, max_steps=5)
