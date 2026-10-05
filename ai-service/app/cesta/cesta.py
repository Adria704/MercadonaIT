"""Dona llena la cesta: presupuesto + personas + dietas -> cesta equilibrada y personalizada.

  * Filtro duro en código: dietas, alergias (incluidas trazas) y productos sensibles. Nunca lo decide el LLM.
  * Personalizada: dentro de cada sección elige lo más afín al cliente (sus compras y sus gustos iniciales).
  * Equilibrada: va rotando por secciones (verdura, proteína, base, fruta, lácteos...) y ajusta cantidades
    al número de personas; al final se acerca todo lo posible al presupuesto sin pasarse.
  * "Otra propuesta": variante > 0 mezcla un poco el orden de forma determinista.
"""
from __future__ import annotations

import zlib

from app import trazas
from app.data import catalogo
from app.perfil import perfil
from app.recsys.recommender import contexto

RONDA = ["Fruta y verdura", "Carne", "Despensa", "Fruta y verdura", "Lácteos y huevos", "Panadería", "Pescado",
         "Despensa", "Listos para comer", "Charcutería", "Bebidas", "Congelados"]
SIN_ALIMENTACION = ("Limpieza", "Higiene")


def _jitter(pid: str, variante: int) -> float:
    return 0.0 if not variante else (zlib.crc32(f"{pid}-{variante}".encode()) % 1000) / 1000 * 0.8


def preparar(cliente_id: str, presupuesto: float, personas: int | None = None, restricciones: list[str] | None = None,
             alergias: list[str] | None = None, variante: int = 0) -> dict:
    if presupuesto is None or presupuesto < 3:
        return {"error": "Con menos de 3 € no da para una cesta"}
    presupuesto = min(float(presupuesto), 300.0)
    cx = contexto(cliente_id)
    cat, af = cx["cat"], cx["afinidad"]
    prefs = dict(cx["prefs"])
    # las dietas de la petición se suman a las guardadas en el perfil del cliente
    prefs["restricciones"] = sorted(set(prefs["restricciones"]) | set(restricciones or []))
    prefs["alergias"] = sorted(set(prefs["alergias"]) | set(alergias or []))
    personas = max(1, min(int(personas or 2), 12))
    habituales = set(cx["peso_compra"])

    principal = cat.sort_index().drop_duplicates("clave").set_index("clave")["id"].to_dict()
    pool = []
    for pid in cx["ids"]:
        row = cat.loc[pid]
        if row.sensible or row.seccion in SIN_ALIMENTACION or pid in prefs["no_me_gusta"]:
            continue
        if pid != principal[row.clave] and pid not in habituales:
            continue
        if perfil.no_apto(row, prefs):
            continue
        pool.append(pid)
    dietas = prefs["restricciones"] + [f"sin {a}" for a in prefs["alergias"]]
    trazas.paso("CESTA", f"Pedido: {presupuesto:.2f} € para {personas} persona{'s' if personas > 1 else ''}"
                         + (f", dietas: {', '.join(dietas)}" if dietas else ", sin restricciones"))
    trazas.paso("CESTA", f"Filtro de alérgenos y dietas (en código, no en la IA): {len(pool)} productos aptos de {len(cx['ids'])}")
    if not pool:
        return {"error": "Ningún producto cumple esas restricciones"}

    score = {p: af.get(p, 0.0) + _jitter(p, variante) for p in pool}
    max_lineas, max_q = min(20, 8 + personas * 3), min(6, max(2, personas + 1))
    lineas: dict[str, int] = {}
    total = 0.0
    precio = {p: float(cat.loc[p, "precio"]) for p in pool}
    claves_usadas: set[str] = set()

    hubo = True
    for _ in range(60):
        if not hubo:
            break
        hubo = False
        for sec in RONDA:
            resto = presupuesto - total
            if len(lineas) < max_lineas:
                nuevos = [p for p in pool if cat.loc[p, "seccion"] == sec and cat.loc[p, "clave"] not in claves_usadas
                          and precio[p] <= resto + 1e-9]
                if nuevos:
                    p = max(nuevos, key=score.get)
                    lineas[p] = 1
                    claves_usadas.add(cat.loc[p, "clave"])
                    total += precio[p]
                    hubo = True
                    continue
            repetir = [p for p in lineas if cat.loc[p, "seccion"] == sec and lineas[p] < max_q and precio[p] <= resto + 1e-9]
            if repetir:
                p = min(repetir, key=lambda x: (lineas[x], -score[x]))
                lineas[p] += 1
                total += precio[p]
                hubo = True
    # remate: acercarse al presupuesto sin pasarse
    for _ in range(40):
        resto = presupuesto - total
        cand = [p for p in pool if precio[p] <= resto + 1e-9 and
                ((p in lineas and lineas[p] < max_q) or (p not in lineas and cat.loc[p, "clave"] not in claves_usadas
                                                         and len(lineas) < max_lineas + 3))]
        if not cand:
            break
        p = max(cand, key=lambda x: (precio[x], score[x]))
        if p not in lineas:
            claves_usadas.add(cat.loc[p, "clave"])
        lineas[p] = lineas.get(p, 0) + 1
        total += precio[p]

    orden = {s: i for i, s in enumerate(dict.fromkeys(RONDA))}
    items = sorted(lineas.items(), key=lambda kv: (orden.get(cat.loc[kv[0], "seccion"], 99), cat.loc[kv[0], "nombre"]))
    total = round(sum(precio[p] * q for p, q in items), 2)
    trazas.paso("CESTA", f"Cesta lista: {len(items)} productos, {total:.2f} € (sobran {presupuesto - total:.2f} €)"
                         + (f", variante {variante}" if variante else ""))
    return {"cesta": {
        "lineas": [{"id": p, "nombre": cat.loc[p, "nombre"], "seccion": cat.loc[p, "seccion"], "cantidad": q,
                    "precio": precio[p], "subtotal": round(precio[p] * q, 2), "habitual": p in habituales} for p, q in items],
        "total": total, "presupuesto": round(presupuesto, 2), "sobra": round(presupuesto - total, 2),
        "personas": personas, "restricciones": prefs["restricciones"], "alergias": prefs["alergias"], "variante": variante,
        "nota": "Lo que es apto lo decide la ficha de alérgenos de cada producto, no la IA.",
    }}


def productos_sueltos(texto: str) -> list[dict]:
    return catalogo.buscar(texto, 5)
