"""Perfil del cliente: cuenta, intereses (onboarding), restricciones y lo que va aprendiendo.

En la arquitectura final las cuentas las gestiona Spring Boot; este módulo lee/escribe las mismas tablas.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import delete, insert, select, text

from app import db, trazas
from app.data import catalogo
from app.data.text import normalize
from app.perfil.intereses import ALERGENOS, INTERESES, RESTRICCIONES


def _row(r) -> dict | None:
    return dict(r._mapping) if r else None


def obtener(cliente_id: str) -> dict | None:
    with db.engine().connect() as c:
        return _row(c.execute(select(db.clientes).where(db.clientes.c.id == cliente_id)).first())


def identificar(telefono: str | None = None, tarjeta_token: str | None = None) -> dict | None:
    """Como en el ticket digital: el cliente se reconoce por teléfono o por el token de su tarjeta."""
    col = db.clientes.c.telefono if telefono else db.clientes.c.tarjeta_token
    with db.engine().connect() as c:
        return _row(c.execute(select(db.clientes).where(col == (telefono or tarjeta_token))).first())


def crear(nombre: str, telefono: str, intereses: list[str], restricciones: list[str] | None = None,
          alergias: list[str] | None = None) -> dict:
    if identificar(telefono=telefono):
        raise ValueError("Ya existe una cuenta con ese teléfono")
    malos = [i for i in intereses if i not in INTERESES]
    if malos:
        raise ValueError(f"Intereses desconocidos: {malos}")
    with db.engine().begin() as c:
        n = c.execute(text("SELECT COUNT(*) FROM clientes WHERE id LIKE 'C%'")).scalar() or 0
        cid = f"C{n + 1:04d}"
        c.execute(insert(db.clientes).values(id=cid, nombre=nombre, telefono=telefono, creado_en=datetime.now(),
                                             tarjeta_token=hashlib.sha256(f"tarjeta-{cid}".encode()).hexdigest()[:32]))
        rows = [{"cliente_id": cid, "tipo": "interes", "valor": v, "peso": 1.0, "origen": "onboarding"} for v in intereses]
        rows += [{"cliente_id": cid, "tipo": "restriccion", "valor": v, "peso": 1.0, "origen": "onboarding"}
                 for v in (restricciones or []) if v in RESTRICCIONES]
        rows += [{"cliente_id": cid, "tipo": "alergia", "valor": v, "peso": 1.0, "origen": "onboarding"}
                 for v in (alergias or []) if v in ALERGENOS]
        if rows:
            c.execute(insert(db.preferencias), rows)
    return obtener(cid)


def preferencias(cliente_id: str) -> dict:
    df = db.query_df("SELECT tipo, valor, peso, origen FROM preferencias WHERE cliente_id = :c", c=cliente_id)
    fb = db.query_df("SELECT producto_id, tipo FROM feedback WHERE cliente_id = :c", c=cliente_id)
    return {
        "intereses": {r.valor: float(r.peso) for r in df.itertuples() if r.tipo == "interes" and r.peso > 0},
        "restricciones": [r.valor for r in df.itertuples() if r.tipo == "restriccion"],
        "alergias": [r.valor for r in df.itertuples() if r.tipo == "alergia"],
        "me_gusta": fb[fb.tipo == "me_gusta"].producto_id.tolist(),
        "no_me_gusta": fb[fb.tipo.isin(["no_me_gusta", "descartar"])].producto_id.tolist(),
    }


def no_apto(row, prefs: dict) -> list[str]:
    """Motivos por los que un producto NO es apto (filtro duro, se decide en código, nunca en el LLM)."""
    motivos = []
    etiquetas = row.etiquetas.split(",")
    if "no_alimentacion" in etiquetas:
        return motivos
    for r in prefs["restricciones"]:
        if r not in RESTRICCIONES:
            continue
        if r == "vegetariano":
            if row.seccion in ("Carne", "Pescado", "Charcutería") or {"pescado", "crustaceos"} & set(row.alergenos.split(",")):
                motivos.append("no es vegetariano")
            continue
        req = RESTRICCIONES[r]["etiqueta_requerida"]
        if req not in etiquetas:
            motivos.append(f"no es {RESTRICCIONES[r]['titulo'].lower()}")
    for a in prefs["alergias"]:
        if a in row.alergenos.split(","):
            motivos.append(f"contiene {a.replace('_', ' ')}")
        elif a in (row.trazas or "").split(","):
            motivos.append(f"puede contener trazas de {a.replace('_', ' ')}")
    return motivos


def _match_interes(texto: str) -> str | None:
    t = normalize(texto)
    for iid, d in INTERESES.items():
        titulo = normalize(d["titulo"])
        if t in (iid, titulo) or titulo in t or (len(t) > 4 and t in titulo):
            return iid
    return None


def _productos_de_grupo(texto: str) -> list[str]:
    """'pescado', 'lácteos', 'bollería'... -> todos los productos de esa sección o categoría."""
    t = normalize(texto).rstrip("s")
    d = catalogo.df()
    for col in ("seccion", "categoria"):
        hit = d[d[col].map(lambda v: t and (t in normalize(v)))]
        if len(hit):
            return hit.id.tolist()
    return []


def actualizar_gustos(cliente_id: str, me_gusta: list[str] | None = None, no_me_gusta: list[str] | None = None) -> dict:
    """Aprende desde el chat: 'me encanta el salmón', 'no me gusta el pescado', 'cocina rápida'."""
    cambios = []
    with db.engine().begin() as c:
        for texto, positivo in [(t, True) for t in (me_gusta or [])] + [(t, False) for t in (no_me_gusta or [])]:
            tipo = "me_gusta" if positivo else "no_me_gusta"
            grupo = _productos_de_grupo(texto)
            if grupo:
                for pid in grupo:
                    c.execute(delete(db.feedback).where((db.feedback.c.cliente_id == cliente_id) & (db.feedback.c.producto_id == pid)))
                    c.execute(insert(db.feedback).values(cliente_id=cliente_id, producto_id=pid, tipo=tipo, fecha=datetime.now()))
                cambios.append({"grupo": texto, "productos": len(grupo), "me_gusta": positivo})
            iid = _match_interes(texto)
            if iid:
                c.execute(delete(db.preferencias).where((db.preferencias.c.cliente_id == cliente_id)
                                                        & (db.preferencias.c.tipo == "interes") & (db.preferencias.c.valor == iid)))
                c.execute(insert(db.preferencias).values(cliente_id=cliente_id, tipo="interes", valor=iid,
                                                         peso=1.5 if positivo else 0.0, origen="chat"))
                cambios.append({"interes": INTERESES[iid]["titulo"], "me_gusta": positivo})
            if grupo or iid:
                continue
            prods = catalogo.buscar(texto, 3)
            if not prods:
                continue
            clave = catalogo.df().loc[prods[0]["id"], "clave"]
            for pid in catalogo.df()[catalogo.df().clave == clave].id:  # todas las variantes del producto
                c.execute(delete(db.feedback).where((db.feedback.c.cliente_id == cliente_id) & (db.feedback.c.producto_id == pid)))
                c.execute(insert(db.feedback).values(cliente_id=cliente_id, producto_id=pid, tipo=tipo, fecha=datetime.now()))
            cambios.append({"producto": prods[0]["nombre"], "me_gusta": positivo})
    for ch in cambios:
        que = ch.get("interes") or ch.get("producto") or f"{ch.get('grupo')} ({ch.get('productos')} productos)"
        trazas.paso("GUSTOS", f"{'Le gusta' if ch['me_gusta'] else 'No le gusta'}: {que} -> guardado en feedback/preferencias")
    return {"actualizado": bool(cambios), "cambios": cambios}
