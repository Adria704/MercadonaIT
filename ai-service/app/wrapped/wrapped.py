"""Wrapped: "Tu año (o tu mes) en el súper".

Reparto de tareas:
  * El CÓDIGO calcula todas las cifras (nunca las inventa el LLM).
  * El LLM solo redacta las tarjetas con gracia a partir de esas cifras (con plantilla si no hay LLM).
Privacidad:
  * Los productos sensibles (salud íntima, etc.) se excluyen de TODO el Wrapped.
  * Las tarjetas "compartibles" no llevan importes en euros.
  * Las comparativas solo se muestran si hay al menos MIN_HOGARES hogares para comparar (anonimato).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.config import hoy
from app.data.calendar_es import DIAS, MESES
from app.db import query_df
from app.llm.gateway import gateway
from app.reciclaje.reciclaje import resumen_cliente

MIN_HOGARES = 50


def _periodo(periodo: str | None) -> tuple[date, date, str]:
    """'2026' -> año natural · '2026-09' -> mes · None/'ultimo_año' -> últimos 365 días."""
    if periodo and len(periodo) == 4:
        y = int(periodo)
        return date(y, 1, 1), date(y + 1, 1, 1), f"tu {y}"
    if periodo and len(periodo) == 7:
        y, m = map(int, periodo.split("-"))
        fin = date(y + (m == 12), m % 12 + 1, 1)
        return date(y, m, 1), fin, f"tu {MESES[m - 1]} de {y}"
    fin = hoy() + timedelta(days=1)
    return fin - timedelta(days=365), fin, "tu último año"


def _lineas(cliente_id: str, desde: date, hasta: date) -> pd.DataFrame:
    return query_df("""
        SELECT t.id AS ticket_id, t.fecha, t.total, l.producto_id, l.cantidad, l.precio_unitario,
               p.nombre, p.clave, p.seccion, p.categoria, p.sensible
        FROM tickets t JOIN lineas_ticket l ON l.ticket_id = t.id JOIN productos p ON p.id = l.producto_id
        WHERE t.cliente_id = :c AND t.fecha >= :d AND t.fecha < :h""", c=cliente_id, d=desde, h=hasta)


def _racha_semanas(fechas: pd.Series) -> int:
    semanas = sorted({(f.isocalendar().year, f.isocalendar().week) for f in fechas})
    best = cur = 1 if semanas else 0
    for a, b in zip(semanas, semanas[1:]):
        consecutiva = (b[0] == a[0] and b[1] == a[1] + 1) or (b[0] == a[0] + 1 and b[1] == 1 and a[1] >= 52)
        cur = cur + 1 if consecutiva else 1
        best = max(best, cur)
    return best


def _percentil_fruta(cliente_id: str, desde: date, hasta: date) -> int | None:
    df = query_df("""
        SELECT t.cliente_id, p.seccion, SUM(l.cantidad) AS uds
        FROM tickets t JOIN lineas_ticket l ON l.ticket_id = t.id JOIN productos p ON p.id = l.producto_id
        WHERE t.fecha >= :d AND t.fecha < :h AND p.sensible = :f
        GROUP BY t.cliente_id, p.seccion""", d=desde, h=hasta, f=False)
    tot = df.groupby("cliente_id").uds.sum()
    fv = df[df.seccion == "Fruta y verdura"].groupby("cliente_id").uds.sum().reindex(tot.index, fill_value=0)
    share = (fv / tot)[tot >= 20]
    if cliente_id not in share.index or len(share) < MIN_HOGARES:
        return None
    return int(round((share < share[cliente_id]).mean() * 100))


def estadisticas(cliente_id: str, periodo: str | None = None) -> dict:
    desde, hasta, etiqueta = _periodo(periodo)
    df = _lineas(cliente_id, desde, hasta)
    df = df[~df.sensible.astype(bool)]  # privacidad: fuera productos sensibles
    if df.empty:
        return {"periodo": etiqueta, "vacio": True}
    tickets = df.drop_duplicates("ticket_id")
    por_clave = df.groupby(["clave"]).agg(uds=("cantidad", "sum"), nombre=("nombre", "first"),
                                          veces=("ticket_id", "nunique")).sort_values("veces", ascending=False)
    primeras = query_df("""SELECT p.clave, MIN(t.fecha) AS fecha_primera FROM tickets t
                           JOIN lineas_ticket l ON l.ticket_id = t.id JOIN productos p ON p.id = l.producto_id
                           WHERE t.cliente_id = :c GROUP BY p.clave""", c=cliente_id)
    # "nuevo" = primera compra dentro del periodo y al menos 60 días después de su primer ticket
    #  (si no, al principio del historial todo parecería nuevo)
    inicio_cliente = primeras.fecha_primera.min() + pd.Timedelta(days=60)
    nuevos = primeras[(primeras.fecha_primera >= max(pd.Timestamp(desde), inicio_cliente))
                      & (primeras.fecha_primera < pd.Timestamp(hasta))]
    claves = set(df.clave)
    cebolla = None
    if {"huevos", "patata"} <= claves:
        cebolla = "con cebolla" if "cebolla" in claves else "sin cebolla"
    horas = tickets.fecha.dt.hour
    franja = "por la mañana" if horas.median() < 13 else ("a mediodía" if horas.median() < 17 else "por la tarde")
    gasto_seccion = (df.cantidad * df.precio_unitario).groupby(df.seccion).sum().sort_values(ascending=False)
    rec = resumen_cliente(cliente_id, desde, hasta)
    return {
        "periodo": etiqueta, "vacio": False,
        "compras": int(len(tickets)),
        "productos_distintos": int(len(claves)),
        "top_productos": [{"nombre": r.nombre, "veces": int(r.veces)} for r in por_clave.head(5).itertuples()],
        "producto_obsesion": {"nombre": por_clave.iloc[0].nombre, "veces": int(por_clave.iloc[0].veces)},
        "seccion_favorita": gasto_seccion.index[0],
        "dia_favorito": DIAS[int(tickets.fecha.dt.weekday.mode().iloc[0])],
        "franja_favorita": franja,
        "racha_semanas": _racha_semanas(tickets.fecha),
        "productos_nuevos": int(len(nuevos)),
        "tortilla": cebolla,
        "reciclaje": rec["por_contenedor"],
        "percentil_fruta": _percentil_fruta(cliente_id, desde, hasta),
        # privado (no compartible):
        "gasto_total": round(float(tickets.total.sum()), 2),
        "gasto_por_seccion": {k: round(float(v), 2) for k, v in gasto_seccion.head(5).items()},
    }


class Tarjeta(BaseModel):
    titulo: str
    texto: str


class WrappedTexto(BaseModel):
    titular: str
    tarjetas: list[Tarjeta]


SISTEMA = ("Eres el redactor de un 'Wrapped' de supermercado, estilo Spotify Wrapped. Español de España, tono divertido, "
           "cercano y breve (máx. 25 palabras por tarjeta). Usa SOLO las cifras que te dan, sin inventar nada. "
           "NO menciones dinero ni euros. Puedes hacer guiños valencianos con moderación.")


def _plantilla(st: dict) -> dict:
    t = [
        {"titulo": "Tu producto obsesión", "texto": f"{st['producto_obsesion']['nombre']}: {st['producto_obsesion']['veces']} veces en tu cesta. Es amor."},
        {"titulo": "Tu ritmo", "texto": f"{st['compras']} compras, sobre todo los {st['dia_favorito']} {st['franja_favorita']}. Racha máxima: {st['racha_semanas']} semanas seguidas."},
        {"titulo": "Explorador", "texto": f"Has probado {st['productos_nuevos']} productos nuevos; en total, {st['productos_distintos']} distintos."},
        {"titulo": "Tu sección", "texto": f"Tu territorio es {st['seccion_favorita']}."},
    ]
    if st.get("tortilla"):
        t.append({"titulo": "El gran debate", "texto": f"Los datos no mienten: eres team tortilla {st['tortilla']}."})
    if (st.get("percentil_fruta") or 0) >= 50:  # solo mensajes positivos, sin juzgar
        t.append({"titulo": "Fruta y verdura", "texto": f"Compras más fruta y verdura que el {st['percentil_fruta']} % de los hogares."})
    if st.get("reciclaje"):
        am = st["reciclaje"].get("amarillo", 0)
        t.append({"titulo": "Reciclaje", "texto": f"Unos {am} envases para el amarillo. El planeta te lo agradece."})
    return {"titular": f"Así ha sido {st['periodo']} en el súper", "tarjetas": t}


def generar(cliente_id: str, periodo: str | None = None, usar_llm: bool = True) -> dict:
    st = estadisticas(cliente_id, periodo)
    if st.get("vacio"):
        return {"periodo": st["periodo"], "titular": "Aún no hay compras en este periodo", "tarjetas": [], "estadisticas": st}
    compartible = {k: v for k, v in st.items() if k not in ("gasto_total", "gasto_por_seccion")}
    if (compartible.get("percentil_fruta") or 0) < 50:
        compartible.pop("percentil_fruta", None)
    texto = _plantilla(st)
    proveedor = "plantilla"
    if usar_llm:
        res = gateway.complete_json(
            [{"role": "user", "content": f"Escribe un titular y entre 5 y 7 tarjetas a partir de estos datos:\n{compartible}"}],
            schema=WrappedTexto, system=SISTEMA, fallback=texto)
        proveedor = res.pop("_proveedor", "llm")
        if res.get("tarjetas"):
            texto = {"titular": res["titular"], "tarjetas": res["tarjetas"]}
    # tarjeta privada con el gasto (solo la ve el cliente, nunca se comparte)
    privada = {"titulo": "Solo para ti", "texto": f"Has gastado {st['gasto_total']:.2f} € en {st['compras']} compras."}
    return {"periodo": st["periodo"], **texto, "tarjeta_privada": privada, "estadisticas": st,
            "compartible": {"titular": texto["titular"], "tarjetas": texto["tarjetas"]}, "redactado_por": proveedor}
