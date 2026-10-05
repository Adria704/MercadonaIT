"""Onboarding "tipo Pinterest": al crear la cuenta el cliente elige tarjetas de intereses.

Cada interés es un conjunto de reglas sobre el catálogo; su vector de gustos es la media de los embeddings
de los productos que cumplen esas reglas (así el arranque en frío vive en el mismo espacio que las compras).
Las RESTRICCIONES (vegano, sin gluten, alergias) no son gustos: son filtros duros que nunca se saltan.
"""
from __future__ import annotations

INTERESES: dict[str, dict] = {
    "desayunos": {"titulo": "Desayunos completos", "emoji": "☕", "descripcion": "Café, tostadas, fruta y cereales",
                  "reglas": {"categorias": ["Desayuno", "Café e infusiones", "Leche", "Pan", "Zumos"], "claves": ["platano"]}},
    "fitness": {"titulo": "Vida fitness", "emoji": "💪", "descripcion": "Proteína, avena y comida limpia",
                "reglas": {"claves": ["yogur_proteina", "pollo", "huevos", "cereales", "arroz", "pavo", "atun", "aguacate", "salmon"]}},
    "fruta_verdura": {"titulo": "Fruta y verdura", "emoji": "🥬", "descripcion": "Producto fresco de temporada",
                      "reglas": {"secciones": ["Fruta y verdura"]}},
    "cocina_rapida": {"titulo": "Cocina en 15 minutos", "emoji": "⏱️", "descripcion": "Platos listos y recetas exprés",
                      "reglas": {"secciones": ["Listos para comer"], "claves": ["pasta", "espagueti", "tomate_frito", "huevos"]}},
    "mediterranea": {"titulo": "Mediterránea", "emoji": "🫒", "descripcion": "Aceite, legumbres, pescado y verdura",
                     "reglas": {"claves": ["aceite", "garbanzo", "lenteja", "tomate", "merluza", "arroz", "pimiento", "judia", "limon"]}},
    "mar_pescado": {"titulo": "Mar y pescado", "emoji": "🐟", "descripcion": "Pescado fresco y marisco",
                    "reglas": {"secciones": ["Pescado"], "claves": ["atun", "gamba"]}},
    "vegetal": {"titulo": "Cocina vegetal", "emoji": "🌱", "descripcion": "Legumbres, hummus y bebidas vegetales",
                "reglas": {"etiquetas": ["vegano"], "secciones": ["Despensa", "Listos para comer", "Lácteos y huevos"]}},
    "dulce": {"titulo": "Un capricho dulce", "emoji": "🍫", "descripcion": "Bollería, chocolate y helado",
              "reglas": {"categorias": ["Bollería", "Cacao", "Helados", "Dulces navideños", "Dulces de temporada"]}},
    "aperitivo": {"titulo": "Aperitivo y planes", "emoji": "🍻", "descripcion": "Para picar con amigos",
                  "reglas": {"categorias": ["Aperitivos", "Cerveza", "Curados", "Quesos", "Refrescos"]}},
    "familia": {"titulo": "Compra familiar", "emoji": "👨‍👩‍👧", "descripcion": "Básicos en formato ahorro",
                "reglas": {"nombre_contiene": ["formato ahorro"]}},
    "cuidado_personal": {"titulo": "Cuidado personal", "emoji": "🧴", "descripcion": "Higiene y cosmética",
                         "reglas": {"secciones": ["Higiene"]}},
    "hogar": {"titulo": "Casa reluciente", "emoji": "🧽", "descripcion": "Limpieza del hogar",
              "reglas": {"secciones": ["Limpieza"]}},
}

RESTRICCIONES = {
    "vegano": {"titulo": "Vegano", "etiqueta_requerida": "vegano"},
    "sin_gluten": {"titulo": "Sin gluten", "etiqueta_requerida": "sin_gluten"},
    "vegetariano": {"titulo": "Vegetariano", "etiqueta_requerida": None},  # sin carne ni pescado
}
ALERGENOS = ["gluten", "lactosa", "huevo", "pescado", "crustaceos", "frutos_secos", "sesamo"]


def productos_de_interes(catalogo, interes_id: str) -> list[str]:
    """Ids de producto que cumplen las reglas de un interés (catalogo: DataFrame de productos)."""
    r = INTERESES[interes_id]["reglas"]
    mask = None
    for col, key in (("seccion", "secciones"), ("categoria", "categorias"), ("clave", "claves")):
        if key in r:
            m = catalogo[col].isin(r[key])
            mask = m if mask is None else (mask | m)
    if "nombre_contiene" in r:
        m = catalogo.nombre.str.contains("|".join(r["nombre_contiene"]), case=False)
        mask = m if mask is None else (mask | m)
    if "etiquetas" in r:
        m = catalogo.etiquetas.apply(lambda e: all(t in e.split(",") for t in r["etiquetas"]))
        mask = m if mask is None else (mask & m)
    sel = catalogo[mask] if mask is not None else catalogo.iloc[0:0]
    return sel[~sel.sensible.astype(bool)].id.tolist()


def tarjetas_onboarding(catalogo) -> list[dict]:
    out = []
    for iid, d in INTERESES.items():
        ejemplos = catalogo[catalogo.id.isin(productos_de_interes(catalogo, iid))].drop_duplicates("clave").head(3)
        out.append({"id": iid, "titulo": d["titulo"], "emoji": d["emoji"], "descripcion": d["descripcion"],
                    "ejemplos": ejemplos.nombre.tolist()})
    return out
