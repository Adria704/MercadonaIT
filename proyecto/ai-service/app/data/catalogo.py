"""Catálogo en memoria (se recarga con recargar()) y búsqueda de productos."""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from app.data.text import BM25, tokenize
from app.db import query_df


@lru_cache(maxsize=1)
def df() -> pd.DataFrame:
    d = query_df("SELECT * FROM productos")
    d["sensible"] = d.sensible.astype(bool)
    return d.set_index("id", drop=False)


@lru_cache(maxsize=1)
def _index() -> BM25:
    d = df()
    docs = (d.nombre + " " + d.nombre + " " + d.clave.str.replace("_", " ") + " " + d.categoria + " " + d.seccion
            + " " + d.etiquetas.str.replace(",", " ").str.replace("_", " "))
    return BM25(docs.tolist())


def recargar() -> None:
    df.cache_clear()
    _index.cache_clear()


def publico(row: pd.Series) -> dict:
    return {"id": row.id, "nombre": row.nombre, "marca": row.marca, "seccion": row.seccion, "categoria": row.categoria,
            "precio": float(row.precio), "alergenos": [a for a in row.alergenos.split(",") if a],
            "trazas": [a for a in (row.trazas or "").split(",") if a],
            "etiquetas": [e for e in row.etiquetas.split(",") if e]}


def producto(pid: str) -> dict:
    return publico(df().loc[pid])


def buscar(consulta: str, limite: int = 8, incluir_sensibles: bool = False) -> list[dict]:
    d = df()
    hits = _index().top(consulta, k=60)
    q = set(tokenize(consulta))
    # bonus si la clave del producto coincide con la consulta ("tomate" -> Tomate pera antes que Tomate frito)
    hits = sorted(((i, s + (2.0 if set(tokenize(d.iloc[i].clave.replace("_", " "))) <= q else 0.0)) for i, s in hits),
                  key=lambda t: t[1], reverse=True)
    out = []
    for i, _ in hits:
        row = d.iloc[i]
        if row.sensible and not incluir_sensibles:
            continue
        out.append(publico(row))
        if len(out) >= limite:
            break
    return out


def resolver(texto_o_id: str) -> dict | None:
    if texto_o_id in df().index:
        return producto(texto_o_id)
    r = buscar(texto_o_id, 1, incluir_sensibles=True)
    return r[0] if r else None


def envase(pid: str) -> list:
    return json.loads(df().loc[pid, "envase"] or "[]")
