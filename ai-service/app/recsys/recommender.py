"""Recomendador que se adapta: empieza por lo que elegiste en el onboarding y pasa a tus compras reales.

    vector_cliente = (1 - α) · gustos_iniciales + α · compras_recientes + ajustes por "me gusta / no me gusta"
    α = nº tickets / (nº tickets + K)          -> 0 al crear la cuenta, tiende a 1 cuanto más compras

Tres listas, siempre con su motivo:
  * lo_de_siempre : lo que compras con regularidad
  * para_ti       : lo más afín a tu vector (puedes haberlo comprado alguna vez)
  * descubre      : productos que NUNCA has comprado, de categorías distintas, con algo de azar diario
                    (para que siempre haya recomendaciones nuevas)
Filtros duros en código: restricciones, alergias (incluidas trazas), productos sensibles y descartados.
Embeddings: models/item_embeddings.npy (PyTorch). Si no existen, SVD de co-ocurrencias (sin PyTorch).
"""
from __future__ import annotations

import json
import logging
import zlib
from datetime import timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from app import trazas
from app.config import hoy, settings
from app.data import catalogo
from app.db import query_df
from app.perfil import perfil
from app.perfil.intereses import INTERESES, productos_de_interes

log = logging.getLogger("recsys")
K_ADAPT = 8          # con 8 tickets, mitad gustos iniciales y mitad compras
DECAY_DIAS = 120     # las compras recientes pesan más


@lru_cache(maxsize=1)
def embeddings() -> tuple[np.ndarray, list[str], dict[str, int], str]:
    f, fi = settings.models_dir / "item_embeddings.npy", settings.models_dir / "item_ids.json"
    if f.exists() and fi.exists():
        ids = json.loads(fi.read_text())
        return np.load(f), ids, {p: i for i, p in enumerate(ids)}, "item2vec (PyTorch)"
    log.warning("No hay embeddings entrenados: uso SVD de co-ocurrencias. Ejecuta `python -m app.recsys.train`.")
    df = query_df("SELECT ticket_id, producto_id FROM lineas_ticket")
    ids = sorted(df.producto_id.unique())
    idx = {p: i for i, p in enumerate(ids)}
    rows = df.ticket_id.astype("category").cat.codes.to_numpy()
    m = np.zeros((rows.max() + 1, len(ids)), dtype=np.float32)
    m[rows, df.producto_id.map(idx).to_numpy()] = 1
    co = m.T @ m
    np.fill_diagonal(co, 0)
    u, s, _ = np.linalg.svd(np.log1p(co), full_matrices=False)
    e = u[:, :32] * np.sqrt(s[:32])
    return e / np.linalg.norm(e, axis=1, keepdims=True), ids, idx, "SVD (sin PyTorch)"


def recargar() -> None:
    embeddings.cache_clear()


def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _compras(cliente_id: str):
    desde = hoy() - timedelta(days=365)
    return query_df("""SELECT l.producto_id, l.cantidad, t.fecha, t.id AS ticket_id FROM lineas_ticket l
                       JOIN tickets t ON t.id = l.ticket_id WHERE t.cliente_id = :c AND t.fecha >= :d""", c=cliente_id, d=desde)


def contexto(cliente_id: str) -> dict:
    """Vector de gustos del cliente y afinidad por producto. Lo usan recomendar() y la cesta de Dona."""
    E, ids, idx, metodo = embeddings()
    cat = catalogo.df()
    prefs = perfil.preferencias(cliente_id)
    compras = _compras(cliente_id)
    compras = compras[compras.producto_id.isin(idx)]
    n_tickets = compras.ticket_id.nunique()
    alpha = n_tickets / (n_tickets + K_ADAPT)

    # --- vector de gustos iniciales (onboarding)
    v_int, vec_interes = np.zeros(E.shape[1]), {}
    for iid, peso in prefs["intereses"].items():
        if iid not in INTERESES:
            continue
        pids = [p for p in productos_de_interes(cat, iid) if p in idx]
        if pids:
            vec_interes[iid] = _norm(E[[idx[p] for p in pids]].mean(0))
            v_int += peso * vec_interes[iid]
    # --- vector de compras con decaimiento temporal
    v_comp = np.zeros(E.shape[1])
    peso_compra: dict[str, float] = {}
    if len(compras):
        dias = (pd.Timestamp(hoy()) - compras.fecha).dt.days.to_numpy()
        w = compras.cantidad.to_numpy() * np.exp(-dias / DECAY_DIAS)
        for pid, wi in zip(compras.producto_id, w):
            peso_compra[pid] = peso_compra.get(pid, 0) + wi
        v_comp = sum(wi * E[idx[p]] for p, wi in peso_compra.items())
    u = (1 - alpha) * _norm(v_int) + alpha * _norm(v_comp)
    for p in prefs["me_gusta"]:
        if p in idx:
            u = u + 0.3 * E[idx[p]]
    for p in prefs["no_me_gusta"]:
        if p in idx:
            u = u - 0.3 * E[idx[p]]
    u = _norm(u)
    scores = E @ u if np.linalg.norm(u) > 0 else np.zeros(len(ids))

    # --- empujón directo a los productos de los intereses elegidos: decide en el arranque en frío
    #     y nunca desaparece del todo (tus gustos declarados siguen contando aunque compres mucho)
    boost: dict[str, float] = {}
    for iid, peso in prefs["intereses"].items():
        if iid not in INTERESES:
            continue
        for p in productos_de_interes(cat, iid):
            boost[p] = max(boost.get(p, 0.0), min(peso, 1.5))
    beta = 0.15 + 0.6 * (1 - alpha)
    afinidad = {pid: float(scores[i]) + beta * boost.get(pid, 0.0) for i, pid in enumerate(ids)}
    gustos = ", ".join(INTERESES[i]["titulo"] for i in prefs["intereses"] if i in INTERESES) or "ninguno"
    filtros = prefs["restricciones"] + [f"sin {a}" for a in prefs["alergias"]]
    trazas.paso("BD", f"Historial de {cliente_id}: {n_tickets} compras, {len(peso_compra)} productos distintos")
    trazas.paso("BD", trazas.recortar(f"Gustos: {gustos}" + (f" | Filtros: {', '.join(filtros)}" if filtros else "")
                                      + (f" | Descartados: {len(prefs['no_me_gusta'])}" if prefs["no_me_gusta"] else ""), 100))
    trazas.paso("MODELO", f"{metodo}: pesan {alpha:.0%} sus compras y {1 - alpha:.0%} sus gustos iniciales")
    return {"E": E, "ids": ids, "idx": idx, "metodo": metodo, "cat": cat, "prefs": prefs, "compras": compras,
            "n_tickets": n_tickets, "alpha": alpha, "u": u, "vec_interes": vec_interes, "peso_compra": peso_compra,
            "boost": boost, "afinidad": afinidad}


def recomendar(cliente_id: str, n: int = 6) -> dict:
    cx = contexto(cliente_id)
    E, ids, idx, metodo, cat, prefs = cx["E"], cx["ids"], cx["idx"], cx["metodo"], cx["cat"], cx["prefs"]
    compras, n_tickets, alpha, u = cx["compras"], cx["n_tickets"], cx["alpha"], cx["u"]
    vec_interes, peso_compra, boost = cx["vec_interes"], cx["peso_compra"], cx["boost"]
    # una variante por producto: la principal, salvo que el cliente compre otra concreta
    principal = cat.sort_index().drop_duplicates("clave").set_index("clave")["id"].to_dict()

    # --- candidatos (filtros duros)
    descartados = set(prefs["no_me_gusta"])
    candidatos = []
    for pid in ids:
        row = cat.loc[pid]
        if row.sensible or pid in descartados or perfil.no_apto(row, prefs):
            continue
        if pid != principal[row.clave] and pid not in peso_compra:
            continue
        candidatos.append((cx["afinidad"][pid], pid))
    candidatos.sort(reverse=True)

    # --- lo de siempre: claves compradas en >= 3 tickets
    claves_compradas = {}
    if len(compras):
        tmp = compras.assign(clave=compras.producto_id.map(cat.clave))
        claves_compradas = tmp.groupby("clave").ticket_id.nunique().sort_values(ascending=False).to_dict()
    habituales = [k for k, v in claves_compradas.items() if v >= 3]
    # Ritmo de cada habitual: cada cuántos días lo compra y hace cuántos que no -> "te toca reponer"
    ritmo = {}
    if len(compras):
        tmp = compras.assign(clave=compras.producto_id.map(cat.clave), dia=compras.fecha.dt.normalize())
        hoy_ts = pd.Timestamp(hoy())
        for k in habituales:
            dias = tmp[tmp.clave == k].dia.drop_duplicates().sort_values()
            cada = float(dias.diff().dt.days.dropna().median()) if len(dias) > 1 else None
            desde = int((hoy_ts - dias.iloc[-1]).days)
            ritmo[k] = {"cada_dias": round(cada) if cada else None, "dias_desde": desde,
                        "progreso": round(min(desde / cada, 1.5), 2) if cada else 0.0}
    # Si hace mucho más de lo normal que no lo compra (temporada pasada o lo dejó), ya no es "lo de siempre"
    habituales = [k for k in habituales if not ritmo.get(k, {}).get("cada_dias")
                  or ritmo[k]["dias_desde"] <= max(2.5 * ritmo[k]["cada_dias"], 21)]
    habituales.sort(key=lambda k: (-(ritmo.get(k, {}).get("progreso", 0) >= 0.85), -claves_compradas[k]))
    lo_de_siempre = []
    for k in habituales[:n]:
        pid = compras[compras.producto_id.map(cat.clave) == k].producto_id.mode().iloc[0]
        r = ritmo.get(k, {})
        toca = r.get("progreso", 0) >= 0.85
        if r.get("cada_dias"):
            motivo = (f"Sueles comprarlo cada {r['cada_dias']} días y hace {r['dias_desde']} que no"
                      if r["dias_desde"] else f"Sueles comprarlo cada {r['cada_dias']} días; lo compraste hoy")
        else:
            motivo = f"Lo compras a menudo ({claves_compradas[k]} veces este año)"
        lo_de_siempre.append({**catalogo.producto(pid), "motivo": motivo, "veces": int(claves_compradas[k]),
                              "toca_reponer": toca, **r})

    def motivo(pid: str, nuevo: bool) -> str:
        e = E[idx[pid]]
        if peso_compra and alpha >= 0.3 and boost.get(pid, 0) == 0:
            top = sorted(peso_compra, key=peso_compra.get, reverse=True)[:12]  # solo lo que compras de verdad
            top = [p for p in top if cat.loc[p, "clave"] != cat.loc[pid, "clave"]]
            if top:
                best = max(top, key=lambda p: float(E[idx[p]] @ e))
                pref = "Nuevo para ti: va genial con" if nuevo else "Porque sueles comprar"
                return f"{pref} «{cat.loc[best, 'nombre']}»"
        en_interes = [k for k in prefs["intereses"] if k in INTERESES and pid in set(productos_de_interes(cat, k))]
        if en_interes:
            return f"Porque te interesa «{INTERESES[en_interes[0]]['titulo']}»"
        if vec_interes:
            best_i = max(vec_interes, key=lambda k: float(vec_interes[k] @ e))
            return f"Encaja con «{INTERESES[best_i]['titulo']}»"
        return "Popular entre hogares parecidos al tuyo"

    def elegir(pool, k, max_por_categoria, excluir_claves):
        out, usadas, por_cat = [], set(excluir_claves), {}
        for _, pid in pool:
            row = cat.loc[pid]
            if row.clave in usadas or por_cat.get(row.categoria, 0) >= max_por_categoria:
                continue
            usadas.add(row.clave)
            por_cat[row.categoria] = por_cat.get(row.categoria, 0) + 1
            out.append(pid)
            if len(out) >= k:
                break
        return out

    para_ti = elegir(candidatos, n, 2, habituales)
    # descubre: nunca comprado, 1 por categoría, con azar diario entre los 25 mejores (siempre hay novedades)
    quiere_no_alim = bool({"cuidado_personal", "hogar"} & set(prefs["intereses"]))
    nunca = [(s, p) for s, p in candidatos if cat.loc[p, "clave"] not in claves_compradas
             and (quiere_no_alim or "no_alimentacion" not in cat.loc[p, "etiquetas"])]
    top = nunca[:25]
    rng = np.random.default_rng(zlib.crc32(f"{cliente_id}{hoy().isoformat()}".encode()))  # determinista por día
    if top:
        probs = np.exp(np.array([s for s, _ in top]) * 4)
        orden = rng.choice(len(top), size=len(top), replace=False, p=probs / probs.sum())
        top = [top[i] for i in orden]
    descubre = elegir(top, max(3, n // 2), 1, set(habituales) | {cat.loc[p, "clave"] for p in para_ti})

    trazas.paso("RESULTADO", f"{len(lo_de_siempre)} de siempre ({sum(1 for x in lo_de_siempre if x['toca_reponer'])} toca reponer), "
                             f"{len(para_ti)} para ti, {len(descubre)} por descubrir")
    return {
        "lo_de_siempre": lo_de_siempre,
        "para_ti": [{**catalogo.producto(p), "motivo": motivo(p, False)} for p in para_ti],
        "descubre": [{**catalogo.producto(p), "motivo": motivo(p, True)} for p in descubre],
        "adaptacion": {
            "tickets_analizados": int(n_tickets), "peso_gustos_iniciales": round(1 - alpha, 2), "peso_compras": round(alpha, 2),
            "mensaje": (f"Basado en tus gustos iniciales ({(1 - alpha):.0%}) y en "
                        + ("tu primera compra" if n_tickets == 1 else f"tus {n_tickets} compras") + f" ({alpha:.0%})"
                        if n_tickets else "Basado en los gustos que elegiste al crear tu cuenta"),
            "metodo": metodo,
        },
        "filtros": {"restricciones": prefs["restricciones"], "alergias": prefs["alergias"], "descartados": len(descartados)},
    }
