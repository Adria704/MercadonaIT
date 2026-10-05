"""Reciclaje: a qué contenedor va cada envase de lo que has comprado.

Funcionalidad secundaria (no debe eclipsar la idea principal): un resumen por compra
y la pregunta "¿dónde tiro esto?" en el asistente.
Contenedores en España: amarillo (plástico, latas, briks), azul (papel y cartón), verde (vidrio),
orgánico (marrón, donde exista), resto (gris) y punto limpio. Las normas cambian según el municipio.
"""
from __future__ import annotations

import json
from collections import Counter

from app.db import query_df

CONTENEDORES = {
    "amarillo": "Contenedor amarillo (envases de plástico, latas y briks)",
    "azul": "Contenedor azul (papel y cartón)",
    "verde": "Contenedor verde (vidrio)",
    "orgánico": "Contenedor marrón de orgánico (restos de comida)",
    "resto": "Contenedor gris de resto",
    "punto limpio": "Punto limpio",
}
NOTA = "Las normas pueden variar según tu municipio."

# clave de producto -> componentes del envase [(componente, contenedor)]
ENVASES: dict[str, list[tuple[str, str]]] = {
    "leche": [("brik", "amarillo")], "leche_avena": [("brik", "amarillo")], "zumo": [("botella de plástico", "amarillo")],
    "gazpacho": [("brik", "amarillo")], "caldo": [("brik", "amarillo")], "tomate_frito": [("brik", "amarillo")],
    "yogur": [("tarrinas de plástico", "amarillo"), ("faja de cartón", "azul")],
    "yogur_proteina": [("tarrinas de plástico", "amarillo")],
    "huevos": [("huevera de cartón", "azul"), ("cáscaras", "orgánico")],
    "agua": [("botellas de plástico", "amarillo"), ("asa de plástico", "amarillo")],
    "refresco": [("botella de plástico", "amarillo")], "cerveza": [("latas", "amarillo"), ("anillas de plástico", "amarillo")],
    "vino": [("botella de vidrio", "verde"), ("corcho", "resto")], "cava": [("botella de vidrio", "verde"), ("tapón y bozal", "resto")],
    "aceite": [("botella de vidrio", "verde"), ("aceite usado", "punto limpio")],
    "atun": [("latas", "amarillo"), ("faja de cartón", "azul")], "aceitunas": [("lata", "amarillo")],
    "garbanzo": [("bote de vidrio", "verde"), ("tapa metálica", "amarillo")],
    "lenteja": [("bote de vidrio", "verde"), ("tapa metálica", "amarillo")],
    "cafe": [("paquete plástico", "amarillo")], "chocolate_taza": [("caja de cartón", "azul")],
    "cereales": [("caja de cartón", "azul"), ("bolsa interior de plástico", "amarillo")],
    "arroz_inflado": [("caja de cartón", "azul"), ("bolsa interior de plástico", "amarillo")],
    "arroz": [("paquete plástico", "amarillo")], "pasta": [("paquete plástico", "amarillo")],
    "espagueti": [("paquete plástico", "amarillo")], "azafran": [("sobre", "resto")],
    "pan": [("bolsa de papel", "azul")], "pan_molde": [("bolsa de plástico", "amarillo")],
    "croissant": [("bolsa de plástico", "amarillo")], "bunuelo": [("bandeja de plástico", "amarillo")],
    "pizza": [("caja de cartón", "azul"), ("film de plástico", "amarillo")],
    "helado": [("tarrina de plástico", "amarillo")], "gamba": [("bolsa de plástico", "amarillo")],
    "turron": [("caja de cartón", "azul"), ("envoltorio de plástico", "amarillo")],
    "patatas_fritas": [("bolsa", "amarillo")], "frutos_secos": [("bolsa", "amarillo")],
    "hummus": [("tarrina de plástico", "amarillo")], "ensalada_pasta": [("bandeja de plástico", "amarillo")],
    "tortilla": [("bandeja de plástico", "amarillo")],
    "detergente": [("botella de plástico", "amarillo")], "lavavajillas": [("botella de plástico", "amarillo")],
    "papel": [("envoltorio de plástico", "amarillo"), ("tubos de cartón", "azul")],
    "champu": [("bote de plástico", "amarillo")], "crema_solar": [("bote de plástico", "amarillo")],
    "pasta_dientes": [("tubo", "amarillo"), ("caja de cartón", "azul")], "desodorante": [("envase de plástico", "amarillo")],
    "preservativos": [("caja de cartón", "azul")], "test_embarazo": [("caja de cartón", "azul"), ("test", "resto")],
}


def envase_por_defecto(clave: str, seccion: str) -> list[tuple[str, str]]:
    if clave in ENVASES:
        return ENVASES[clave]
    if seccion == "Fruta y verdura":
        return [("bolsa", "amarillo"), ("pieles y restos", "orgánico")]
    if seccion in ("Carne", "Pescado", "Charcutería"):
        return [("bandeja de plástico", "amarillo"), ("restos", "orgánico")]
    if seccion == "Lácteos y huevos":
        return [("envase de plástico", "amarillo")]
    return [("envase", "amarillo")]


def donde_tiro(producto: dict) -> dict:
    comps = json.loads(producto.get("envase") or "[]") if isinstance(producto.get("envase"), str) else producto.get("envase", [])
    return {"producto": producto["nombre"],
            "contenedores": [{"componente": c, "contenedor": k, "detalle": CONTENEDORES.get(k, k)} for c, k in comps],
            "nota": NOTA}


def _contar(df) -> dict:
    cnt: Counter = Counter()
    for envase, cantidad in zip(df.envase, df.cantidad):
        for _, cont in json.loads(envase or "[]"):
            cnt[cont] += int(cantidad)
    return dict(cnt.most_common())


def resumen_ticket(ticket_id: str) -> dict:
    df = query_df("""SELECT p.envase, l.cantidad FROM lineas_ticket l JOIN productos p ON p.id = l.producto_id
                     WHERE l.ticket_id = :t""", t=ticket_id)
    return {"ticket_id": ticket_id, "por_contenedor": _contar(df), "nota": NOTA}


def resumen_cliente(cliente_id: str, desde, hasta) -> dict:
    df = query_df("""SELECT p.envase, l.cantidad FROM lineas_ticket l
                     JOIN tickets t ON t.id = l.ticket_id JOIN productos p ON p.id = l.producto_id
                     WHERE t.cliente_id = :c AND t.fecha >= :d AND t.fecha < :h""", c=cliente_id, d=desde, h=hasta)
    por = _contar(df)
    return {"por_contenedor": por, "envases_totales": sum(v for k, v in por.items() if k not in ("orgánico",)), "nota": NOTA}
