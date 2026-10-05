"""Carga datos SINTÉTICOS en la base de datos (SQLite o PostgreSQL).

  python -m app.data.seed            -> borra y recrea todo (semilla fija)

Genera:
  * catálogo (~135 productos, marcas Hacendado/Deliplus/Bosque Verde; frescos sin marca) con alérgenos,
    trazas, etiquetas, envase y marca de "sensible". Precios inventados.
  * 3 clientes de demo:
      - Laura  (600111222): 1 año de historial, compra entre semana por la tarde, perfil fitness/desayunos
      - Álex   (600333444): estudiante, cocina rápida y aperitivo, compra los fines de semana
      - Carmen (600555666): cuenta NUEVA, solo onboarding (sin gluten) -> demuestra el arranque en frío
  * ~400 hogares de fondo con ~12.000 tickets (para entrenar embeddings y comparativas anónimas)
En la demo decid que los datos son sintéticos. Simulan lo que llegaría desde el ticket digital vía Spring Batch.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete

from app import db
from app.config import hoy
from app.data.calendar_es import is_closed
from app.data.catalogo_base import BUNDLES, PROFILES, build_catalog
from app.reciclaje.reciclaje import envase_por_defecto

SEED = 7
TIENDAS = ["T01", "T02", "T03", "T04", "T05"]

DEMO = [
    {"id": "C0001", "nombre": "Laura", "telefono": "600111222", "tienda": "T02",
     "intereses": ["desayunos", "fitness", "fruta_verdura"], "restricciones": [], "alergias": [],
     "dias_compra": [0, 3, 5], "horas": (19, 21),
     # clave, cada cuántos días, unidades
     "habitos": [("cafe", 10, 1), ("leche", 5, 2), ("platano", 5, 1), ("yogur_proteina", 6, 1), ("pollo", 7, 1),
                 ("huevos", 9, 1), ("cereales", 14, 1), ("manzana", 7, 1), ("pan_molde", 7, 1), ("aguacate", 10, 2),
                 ("salmon", 14, 1), ("arroz", 21, 1), ("tomate", 7, 1), ("papel", 25, 1), ("champu", 40, 1)],
     "ocasionales": ["patata", "cebolla", "queso_curado", "gazpacho", "sandia", "turron", "vino", "preservativos", "helado"]},
    {"id": "C0002", "nombre": "Álex", "telefono": "600333444", "tienda": "T01",
     "intereses": ["cocina_rapida", "aperitivo"], "restricciones": [], "alergias": [],
     "dias_compra": [4, 5], "horas": (12, 14),
     "habitos": [("pasta", 6, 1), ("tomate_frito", 6, 2), ("pizza", 7, 1), ("cerveza", 8, 1), ("patatas_fritas", 8, 1),
                 ("refresco", 7, 1), ("huevos", 14, 1), ("queso_rallado", 12, 1), ("pan", 4, 1), ("tortilla", 10, 1)],
     "ocasionales": ["helado", "aceitunas", "atun", "croissant", "cafe", "lavavajillas"]},
    {"id": "C0003", "nombre": "Carmen", "telefono": "600555666", "tienda": "T03",
     "intereses": ["mediterranea", "mar_pescado"], "restricciones": ["sin_gluten"], "alergias": [],
     "dias_compra": [], "horas": (10, 11), "habitos": [], "ocasionales": []},
]


def _ts(d, rng, horas=(9, 21)) -> datetime:
    return datetime.combine(d, time(int(rng.integers(horas[0], horas[1])), int(rng.integers(0, 60))))


def _catalogo(rng) -> pd.DataFrame:
    cat = build_catalog(rng)
    cat["envase"] = [json.dumps(envase_por_defecto(k, s), ensure_ascii=False) for k, s in zip(cat.clave, cat.seccion)]
    cat["sensible"] = cat.etiquetas.str.contains("sensible") | cat.categoria.isin(["Salud íntima"])
    cat["etiquetas"] = cat.etiquetas.str.replace(",sensible", "", regex=False)
    cat = cat.rename(columns={"peso_g": "formato_g"})
    return cat


def _demo_tickets(c: dict, cat: pd.DataFrame, rng, start, end) -> list[dict]:
    main = cat.drop_duplicates("clave").set_index("clave")
    due = {k: start + timedelta(days=int(rng.integers(0, every))) for k, every, _ in c["habitos"]}
    out, d = [], start
    while d <= end:
        if d.weekday() in c["dias_compra"] and not is_closed(d) and (rng.random() < 0.9 or d > end - timedelta(days=7)):
            items: dict[str, int] = {}
            for k, every, qty in c["habitos"]:
                if due[k] <= d + timedelta(days=1):
                    items[main.loc[k, "id"]] = qty
                    due[k] = d + timedelta(days=int(round(every * rng.uniform(0.85, 1.15))))
            if not items and c["habitos"]:  # nunca un día de compra vacío: adelanta lo más próximo
                k, every, qty = min(c["habitos"], key=lambda h: due[h[0]])
                items[main.loc[k, "id"]] = qty
                due[k] = d + timedelta(days=int(round(every * rng.uniform(0.85, 1.15))))
            for k in c["ocasionales"]:
                p = 0.06
                if k == "sandia":
                    p = 0.35 if d.month in (6, 7, 8) else 0.0
                if k == "turron":
                    p = 0.5 if d.month == 12 else 0.0
                if k in ("patata", "cebolla"):
                    p = 0.2
                if rng.random() < p:
                    items[main.loc[k, "id"]] = 1
            if items:
                out.append({"cliente_id": c["id"], "tienda_id": c["tienda"], "fecha": _ts(d, rng, c["horas"]),
                            "metodo_pago": "tarjeta" if rng.random() < 0.85 else "efectivo", "items": items})
        d += timedelta(days=1)
    return out


def _background(cat: pd.DataFrame, rng, start, end, n_clientes=400) -> tuple[list[dict], list[dict]]:
    by_key = cat.groupby("clave")["id"].apply(list).to_dict()
    food = cat[~cat.sensible]
    open_days = [d.date() for d in pd.date_range(start, end) if not is_closed(d.date())]
    profiles = list(PROFILES)
    clientes, tickets = [], []
    for i in range(n_clientes):
        cid = f"B{i:04d}"
        prof = profiles[rng.choice(len(profiles), p=[0.3, 0.2, 0.15, 0.12, 0.08, 0.15])]
        clientes.append({"id": cid, "nombre": f"Hogar {i}", "telefono": None, "tarjeta_token": None,
                         "creado_en": datetime.combine(start, time(9))})
        pool = food if prof != "vegano" else food[food.etiquetas.str.contains("vegano") | food.etiquetas.str.contains("no_alimentacion")]
        w = pool.seccion.map(lambda s: PROFILES[prof]["pref"].get(s, 1.0)).to_numpy() * pool.demanda_base.to_numpy()
        w = w / w.sum()
        fav_bundles = rng.choice(len(BUNDLES), size=3, replace=False)  # cada hogar tiene sus "recetas" habituales
        for _ in range(int(rng.integers(15, 45))):
            n = max(2, int(rng.integers(*PROFILES[prof]["n"])) // 2)
            items = {pid: int(rng.integers(1, 3)) for pid in rng.choice(pool.id.to_numpy(), size=min(n, len(pool)), replace=False, p=w)}
            for b in fav_bundles:
                if rng.random() < 0.45:
                    for k in BUNDLES[b]:
                        if k in by_key and rng.random() < 0.85:
                            items[by_key[k][0]] = 1
            d = open_days[int(rng.integers(len(open_days)))]
            tickets.append({"cliente_id": cid, "tienda_id": TIENDAS[int(rng.integers(len(TIENDAS)))], "fecha": _ts(d, rng),
                            "metodo_pago": "tarjeta", "items": items})
    return clientes, tickets


def main() -> None:
    rng = np.random.default_rng(SEED)
    end = hoy() - timedelta(days=1)
    start = end - timedelta(days=365)
    db.create_schema()
    eng = db.engine()
    cat = _catalogo(rng)
    price = cat.set_index("id").precio.to_dict()

    demo_tickets = []
    for c in DEMO:
        demo_tickets += _demo_tickets(c, cat, rng, start, end)
    bg_clientes, bg_tickets = _background(cat, rng, start, end)

    with eng.begin() as conn:
        for t in (db.feedback, db.lineas_ticket, db.tickets, db.preferencias, db.clientes, db.productos):
            conn.execute(delete(t))
        cols = [c.name for c in db.productos.columns]
        conn.execute(db.productos.insert(), cat[cols].to_dict(orient="records"))
        now = datetime.combine(start, time(9))
        conn.execute(db.clientes.insert(), [
            {"id": c["id"], "nombre": c["nombre"], "telefono": c["telefono"],
             "tarjeta_token": hashlib.sha256(f"tarjeta-{c['id']}".encode()).hexdigest()[:32],
             "creado_en": now if c["habitos"] else datetime.combine(end, time(10))} for c in DEMO] + bg_clientes)
        prefs = []
        for c in DEMO:
            prefs += [{"cliente_id": c["id"], "tipo": "interes", "valor": v, "peso": 1.0, "origen": "onboarding"} for v in c["intereses"]]
            prefs += [{"cliente_id": c["id"], "tipo": "restriccion", "valor": v, "peso": 1.0, "origen": "onboarding"} for v in c["restricciones"]]
            prefs += [{"cliente_id": c["id"], "tipo": "alergia", "valor": v, "peso": 1.0, "origen": "onboarding"} for v in c["alergias"]]
        conn.execute(db.preferencias.insert(), prefs)

        rows_t, rows_l = [], []
        for i, t in enumerate(sorted(demo_tickets + bg_tickets, key=lambda x: x["fecha"])):
            tid = f"T{i:07d}"
            total = round(sum(price[p] * q for p, q in t["items"].items()), 2)
            rows_t.append({"id": tid, "cliente_id": t["cliente_id"], "tienda_id": t["tienda_id"], "fecha": t["fecha"],
                           "total": total, "metodo_pago": t["metodo_pago"], "origen": "ticket_digital",
                           "hash_dedupe": hashlib.sha256(tid.encode()).hexdigest()})
            rows_l += [{"ticket_id": tid, "producto_id": p, "cantidad": q, "precio_unitario": price[p]} for p, q in t["items"].items()]
        conn.execute(db.tickets.insert(), rows_t)
        conn.execute(db.lineas_ticket.insert(), rows_l)
    n_demo = {c["nombre"]: sum(1 for t in demo_tickets if t["cliente_id"] == c["id"]) for c in DEMO}
    print(f"Productos: {len(cat)} | Tickets: {len(rows_t):,} ({len(rows_l):,} líneas) | Demo: {n_demo} | BD: {db.settings.database_url}")


if __name__ == "__main__":
    main()
