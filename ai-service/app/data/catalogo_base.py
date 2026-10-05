"""Catálogo base SINTÉTICO con las marcas propias de Mercadona (precios, tiendas y clientes inventados).

Reutilizado del kit de hackathon. Aquí solo se usan BASE, BRANDS, BUNDLES, PROFILES, TRAZAS y build_catalog().
--- Documentación original: ---

Genera en data/generated/:
  catalogo.csv   ~250 referencias con precio, formato, nutrición/100 g, alérgenos, etiquetas
  tiendas.csv    tiendas ficticias del área de Valencia
  clientes.csv   perfiles (familia, pareja, estudiante, fitness, vegano, senior)
  ventas.csv     ventas diarias (2 años) de ~60 productos x 5 tiendas, con estacionalidad,
                 domingos/festivos cerrados, vísperas, Fallas, Navidad, tendencia y ruido
  tickets.csv    ~12.000 tickets (líneas) con co-ocurrencias realistas (tortilla, paella, ensalada…)

Uso:  python -m app.data.generate        (semilla fija -> siempre los mismos datos)
IMPORTANTE: en la demo, decid explícitamente que los datos son sintéticos.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.config import settings
from app.data.calendar_es import is_christmas_season, is_closed, is_fallas, is_pre_holiday

SEED = 42

# clave, nombre, sección, categoría, peso_g, precio, kcal, prot, hc, grasa, alérgenos, tags, estación, demanda_base
BASE = [
    # Fruta y verdura
    ("platano", "Plátano de Canarias", "Fruta y verdura", "Fruta", 1000, 2.35, 94, 1.2, 20, 0.3, "", "vegano,sin_gluten,fresco", "flat", 60),
    ("manzana", "Manzana Golden", "Fruta y verdura", "Fruta", 1000, 1.99, 52, 0.3, 14, 0.2, "", "vegano,sin_gluten,fresco", "flat", 45),
    ("naranja", "Naranja de mesa", "Fruta y verdura", "Fruta", 2000, 2.79, 47, 0.9, 12, 0.1, "", "vegano,sin_gluten,fresco", "invierno", 50),
    ("mandarina", "Mandarina", "Fruta y verdura", "Fruta", 1000, 2.25, 53, 0.8, 13, 0.3, "", "vegano,sin_gluten,fresco", "invierno", 35),
    ("sandia", "Sandía sin pepitas", "Fruta y verdura", "Fruta", 3000, 3.60, 30, 0.6, 8, 0.2, "", "vegano,sin_gluten,fresco", "verano", 25),
    ("melon", "Melón piel de sapo", "Fruta y verdura", "Fruta", 2500, 3.10, 34, 0.8, 8, 0.2, "", "vegano,sin_gluten,fresco", "verano", 20),
    ("fresa", "Fresón", "Fruta y verdura", "Fruta", 500, 2.20, 32, 0.7, 8, 0.3, "", "vegano,sin_gluten,fresco", "flat", 22),
    ("tomate", "Tomate pera", "Fruta y verdura", "Verdura", 1000, 1.89, 18, 0.9, 3.9, 0.2, "", "vegano,sin_gluten,fresco", "verano", 55),
    ("lechuga", "Lechuga iceberg", "Fruta y verdura", "Verdura", 500, 0.89, 14, 0.9, 3, 0.1, "", "vegano,sin_gluten,fresco", "verano", 35),
    ("pepino", "Pepino", "Fruta y verdura", "Verdura", 400, 0.69, 15, 0.7, 3.6, 0.1, "", "vegano,sin_gluten,fresco", "verano", 25),
    ("cebolla", "Cebolla", "Fruta y verdura", "Verdura", 2000, 2.10, 40, 1.1, 9, 0.1, "", "vegano,sin_gluten,fresco", "flat", 40),
    ("patata", "Patata", "Fruta y verdura", "Verdura", 3000, 3.20, 77, 2, 17, 0.1, "", "vegano,sin_gluten,fresco", "flat", 40),
    ("pimiento", "Pimiento rojo", "Fruta y verdura", "Verdura", 500, 1.45, 31, 1, 6, 0.3, "", "vegano,sin_gluten,fresco", "verano", 25),
    ("judia", "Judía verde plana", "Fruta y verdura", "Verdura", 500, 1.95, 31, 1.8, 7, 0.2, "", "vegano,sin_gluten,fresco", "flat", 15),
    ("calabacin", "Calabacín", "Fruta y verdura", "Verdura", 600, 1.10, 17, 1.2, 3.1, 0.3, "", "vegano,sin_gluten,fresco", "flat", 20),
    ("aguacate", "Aguacate", "Fruta y verdura", "Fruta", 500, 2.99, 160, 2, 9, 15, "", "vegano,sin_gluten,fresco", "flat", 18),
    ("limon", "Limón", "Fruta y verdura", "Fruta", 500, 1.29, 29, 1.1, 9, 0.3, "", "vegano,sin_gluten,fresco", "flat", 15),
    # Carne y charcutería
    ("pollo", "Pechuga de pollo fileteada", "Carne", "Aves", 500, 3.45, 110, 23, 0, 1.5, "", "sin_gluten,fresco", "flat", 40),
    ("muslo", "Contramuslo de pollo", "Carne", "Aves", 800, 3.60, 180, 18, 0, 12, "", "sin_gluten,fresco", "flat", 20),
    ("ternera", "Filete de añojo", "Carne", "Vacuno", 400, 5.60, 150, 21, 0, 7, "", "sin_gluten,fresco", "flat", 15),
    ("picada", "Carne picada mixta", "Carne", "Picada", 500, 3.25, 220, 17, 0.5, 16, "", "fresco", "flat", 25),
    ("cerdo", "Lomo de cerdo en filetes", "Carne", "Cerdo", 600, 4.10, 145, 21, 0, 6.5, "", "sin_gluten,fresco", "flat", 18),
    ("conejo", "Conejo troceado", "Carne", "Conejo", 900, 6.30, 133, 21, 0, 5.5, "", "sin_gluten,fresco", "flat", 6),
    ("jamon", "Jamón serrano lonchas", "Charcutería", "Curados", 200, 2.95, 250, 30, 0.5, 14, "", "sin_gluten", "navidad_suave", 30),
    ("pavo", "Pechuga de pavo lonchas", "Charcutería", "Cocidos", 250, 2.40, 105, 19, 2, 2, "", "sin_gluten", "flat", 25),
    ("chorizo", "Chorizo extra", "Charcutería", "Curados", 225, 2.10, 400, 24, 2, 33, "", "sin_gluten", "invierno", 12),
    # Pescado
    ("salmon", "Salmón fresco en lomos", "Pescado", "Fresco", 300, 4.95, 208, 20, 0, 13, "pescado", "sin_gluten,fresco", "flat", 15),
    ("merluza", "Merluza en filetes", "Pescado", "Fresco", 400, 4.40, 86, 17, 0, 1.8, "pescado", "sin_gluten,fresco", "flat", 12),
    ("atun", "Atún claro en aceite pack 3", "Despensa", "Conservas", 240, 3.30, 200, 25, 0, 11, "pescado", "sin_gluten", "flat", 30),
    ("langostino", "Langostino cocido", "Pescado", "Marisco", 500, 6.50, 99, 21, 0, 1.5, "crustaceos", "sin_gluten", "navidad", 6),
    ("gamba", "Gamba pelada congelada", "Congelados", "Marisco", 400, 4.20, 85, 18, 0, 1, "crustaceos", "sin_gluten", "flat", 10),
    # Lácteos y huevos
    ("leche", "Leche semidesnatada", "Lácteos y huevos", "Leche", 1000, 0.95, 46, 3.1, 4.7, 1.6, "lactosa", "sin_gluten", "flat", 90),
    ("leche_avena", "Bebida de avena", "Lácteos y huevos", "Bebidas vegetales", 1000, 1.25, 45, 0.7, 7, 1.4, "gluten", "vegano", "flat", 20),
    ("yogur", "Yogur natural pack 6", "Lácteos y huevos", "Yogures", 750, 1.35, 61, 3.8, 4.5, 3.2, "lactosa", "sin_gluten", "flat", 45),
    ("yogur_proteina", "Yogur alto en proteínas", "Lácteos y huevos", "Yogures", 500, 2.10, 60, 10, 4, 0.2, "lactosa", "sin_gluten", "flat", 20),
    ("queso_rallado", "Queso rallado mezcla", "Lácteos y huevos", "Quesos", 200, 1.85, 380, 26, 1.5, 30, "lactosa", "sin_gluten", "flat", 25),
    ("queso_curado", "Queso curado cuña", "Lácteos y huevos", "Quesos", 350, 4.90, 410, 27, 0.5, 34, "lactosa", "sin_gluten", "navidad_suave", 15),
    ("huevos", "Huevos frescos L docena", "Lácteos y huevos", "Huevos", 730, 2.75, 143, 12.6, 0.7, 9.5, "huevo", "sin_gluten,fresco", "flat", 50),
    ("mantequilla", "Mantequilla", "Lácteos y huevos", "Mantequilla", 250, 2.40, 740, 0.6, 0.6, 82, "lactosa", "sin_gluten", "flat", 12),
    ("helado", "Helado de vainilla", "Congelados", "Helados", 900, 2.95, 200, 3.5, 24, 10, "lactosa", "", "verano", 20),
    # Panadería
    ("pan", "Barra de pan", "Panadería", "Pan", 250, 0.60, 260, 9, 52, 1.2, "gluten", "vegano,fresco", "flat", 120),
    ("pan_molde", "Pan de molde integral", "Panadería", "Pan", 460, 1.40, 245, 10, 41, 3.5, "gluten", "vegano", "flat", 30),
    ("croissant", "Croissant pack 6", "Panadería", "Bollería", 300, 1.95, 420, 8, 45, 22, "gluten,lactosa,huevo", "", "flat", 25),
    ("bunuelo", "Buñuelos de calabaza", "Panadería", "Dulces de temporada", 300, 2.60, 330, 5, 45, 14, "gluten,huevo", "", "fallas", 4),
    # Despensa
    ("arroz", "Arroz redondo", "Despensa", "Arroz", 1000, 1.45, 350, 7, 78, 0.6, "", "vegano,sin_gluten", "flat", 35),
    ("pasta", "Macarrones", "Despensa", "Pasta", 1000, 1.10, 355, 12, 72, 1.5, "gluten", "vegano", "flat", 40),
    ("espagueti", "Espagueti", "Despensa", "Pasta", 500, 0.80, 355, 12, 72, 1.5, "gluten", "vegano", "flat", 30),
    ("tomate_frito", "Tomate frito", "Despensa", "Salsas", 400, 0.85, 75, 1.5, 9, 3.5, "", "vegano,sin_gluten", "flat", 40),
    ("garbanzo", "Garbanzo cocido", "Despensa", "Legumbres", 570, 0.95, 120, 7, 15, 2.5, "", "vegano,sin_gluten", "invierno", 20),
    ("lenteja", "Lenteja cocida", "Despensa", "Legumbres", 570, 0.95, 105, 8, 13, 0.5, "", "vegano,sin_gluten", "invierno", 18),
    ("aceite", "Aceite de oliva virgen extra", "Despensa", "Aceites", 1000, 8.95, 900, 0, 0, 100, "", "vegano,sin_gluten", "flat", 25),
    ("azafran", "Colorante y especias para paella", "Despensa", "Especias", 30, 1.10, 300, 10, 50, 5, "", "vegano,sin_gluten", "flat", 8),
    ("caldo", "Caldo de pollo", "Despensa", "Caldos", 1000, 1.30, 8, 0.6, 0.5, 0.4, "", "sin_gluten", "invierno", 18),
    ("cereales", "Copos de avena", "Despensa", "Desayuno", 500, 1.20, 370, 13, 59, 7, "gluten", "vegano", "flat", 25),
    ("arroz_inflado", "Arroz inflado tostado", "Despensa", "Desayuno", 375, 1.60, 380, 7, 84, 1, "", "vegano,sin_gluten", "flat", 12),
    ("cafe", "Café molido natural", "Despensa", "Café e infusiones", 250, 2.95, 2, 0.1, 0, 0, "", "vegano,sin_gluten", "flat", 30),
    ("chocolate_taza", "Chocolate a la taza", "Despensa", "Cacao", 400, 2.30, 380, 6, 70, 8, "lactosa", "", "invierno", 8),
    ("turron", "Turrón de Jijona", "Despensa", "Dulces navideños", 300, 3.90, 560, 14, 40, 38, "frutos_secos", "sin_gluten", "navidad", 5),
    ("aceitunas", "Aceitunas rellenas de anchoa", "Despensa", "Aperitivos", 350, 1.15, 160, 1, 1.5, 16, "pescado", "sin_gluten", "verano", 25),
    ("patatas_fritas", "Patatas fritas onduladas", "Despensa", "Aperitivos", 170, 1.10, 530, 6, 52, 32, "", "vegano,sin_gluten", "verano", 30),
    ("frutos_secos", "Cóctel de frutos secos", "Despensa", "Frutos secos", 200, 2.40, 600, 20, 15, 50, "frutos_secos", "vegano,sin_gluten", "navidad_suave", 15),
    ("hummus", "Hummus clásico", "Listos para comer", "Untables", 240, 1.85, 300, 7, 12, 25, "sesamo", "vegano,sin_gluten", "verano", 18),
    ("gazpacho", "Gazpacho", "Listos para comer", "Cremas frías", 1000, 2.20, 40, 0.8, 4, 2.3, "", "vegano,sin_gluten", "verano", 30),
    ("ensalada_pasta", "Ensalada de pasta", "Listos para comer", "Ensaladas", 300, 2.75, 160, 6, 22, 5, "gluten,huevo", "", "verano", 15),
    ("pizza", "Pizza barbacoa", "Listos para comer", "Pizzas", 440, 3.50, 240, 11, 28, 9, "gluten,lactosa", "", "flat", 25),
    ("tortilla", "Tortilla de patatas con cebolla", "Listos para comer", "Platos preparados", 600, 3.10, 160, 6, 12, 10, "huevo", "sin_gluten", "flat", 20),
    # Bebidas
    ("agua", "Agua mineral 6x1,5 L", "Bebidas", "Agua", 9000, 1.95, 0, 0, 0, 0, "", "vegano,sin_gluten", "verano", 60),
    ("cerveza", "Cerveza lager pack 6", "Bebidas", "Cerveza", 1980, 3.30, 42, 0.3, 3.5, 0, "gluten", "vegano", "verano", 35),
    ("refresco", "Refresco de cola zero 2 L", "Bebidas", "Refrescos", 2000, 1.15, 0, 0, 0, 0, "", "vegano,sin_gluten", "verano", 35),
    ("zumo", "Zumo de naranja exprimido", "Bebidas", "Zumos", 1000, 2.50, 44, 0.7, 10, 0.2, "", "vegano,sin_gluten,fresco", "flat", 20),
    ("cava", "Cava brut", "Bebidas", "Vinos y cavas", 750, 4.50, 70, 0.1, 1.5, 0, "", "vegano,sin_gluten", "navidad", 6),
    ("vino", "Vino tinto D.O.", "Bebidas", "Vinos y cavas", 750, 3.80, 85, 0.1, 2.6, 0, "", "vegano,sin_gluten", "navidad_suave", 15),
    # Limpieza e higiene (no alimentación)
    ("detergente", "Detergente líquido 40 lavados", "Limpieza", "Ropa", 2000, 6.50, 0, 0, 0, 0, "", "no_alimentacion", "flat", 15),
    ("lavavajillas", "Lavavajillas a mano", "Limpieza", "Cocina", 1000, 1.40, 0, 0, 0, 0, "", "no_alimentacion", "flat", 15),
    ("papel", "Papel higiénico 12 rollos", "Limpieza", "Papel", 1500, 4.20, 0, 0, 0, 0, "", "no_alimentacion", "flat", 25),
    ("champu", "Champú uso frecuente", "Higiene", "Cabello", 400, 1.90, 0, 0, 0, 0, "", "no_alimentacion", "flat", 12),
    ("crema_solar", "Crema solar SPF 50", "Higiene", "Solar", 250, 6.90, 0, 0, 0, 0, "", "no_alimentacion", "verano", 6),
    ("pasta_dientes", "Pasta de dientes", "Higiene", "Bucal", 75, 1.30, 0, 0, 0, 0, "", "no_alimentacion", "flat", 15),
    ("desodorante", "Desodorante roll-on", "Higiene", "Corporal", 50, 1.60, 0, 0, 0, 0, "", "no_alimentacion", "flat", 10),
    ("preservativos", "Preservativos pack 12", "Higiene", "Salud íntima", 50, 6.50, 0, 0, 0, 0, "", "no_alimentacion,sensible", "flat", 3),
    ("test_embarazo", "Test de embarazo", "Higiene", "Salud íntima", 30, 5.00, 0, 0, 0, 0, "", "no_alimentacion,sensible", "flat", 1),
]

# "Puede contener trazas de…" (clave -> alérgenos). Clave para el escudo de alérgenos.
TRAZAS = {"cereales": "frutos_secos", "chocolate_taza": "frutos_secos", "croissant": "frutos_secos,sesamo",
          "pan_molde": "sesamo", "helado": "frutos_secos", "galletas": "frutos_secos", "hummus": "frutos_secos"}

# Marcas propias de Mercadona: Hacendado (alimentación), Deliplus (higiene) y Bosque Verde (limpieza).
# Los frescos van sin marca, como en tienda. Un solo producto por marca (sin "segundas marcas" duplicadas).
BRANDS = {
    "Fruta y verdura": [""], "Carne": [""], "Pescado": [""], "Panadería": [""],
    "Charcutería": ["Hacendado"], "Lácteos y huevos": ["Hacendado"], "Despensa": ["Hacendado"],
    "Listos para comer": ["Hacendado"], "Bebidas": ["Hacendado"], "Congelados": ["Hacendado"],
    "Limpieza": ["Bosque Verde"], "Higiene": ["Deliplus"],
}

BUNDLES = [  # co-ocurrencias "recetas"
    ["huevos", "patata", "cebolla", "aceite"],               # tortilla
    ["arroz", "pollo", "judia", "pimiento", "azafran", "aceite"],  # paella
    ["lechuga", "tomate", "pepino", "cebolla", "aceitunas"],  # ensalada
    ["pasta", "tomate_frito", "queso_rallado", "picada"],      # macarrones
    ["espagueti", "tomate_frito", "queso_rallado"],
    ["pan", "jamon", "tomate", "aceite"],                      # pa amb tomaca
    ["leche", "cereales", "platano"],                          # desayuno
    ["cafe", "leche", "croissant"],
    ["cerveza", "patatas_fritas", "aceitunas"],                # aperitivo
    ["yogur_proteina", "pollo", "arroz", "cereales"],          # fitness
    ["garbanzo", "chorizo", "caldo", "patata"],                # cocido
    ["salmon", "limon", "aguacate"],
    ["hummus", "pan", "pepino"],
    ["langostino", "cava", "turron", "jamon"],                 # navidad
    ["gazpacho", "sandia", "agua"],                            # verano
    ["pizza", "refresco", "helado"],
]

PROFILES = {
    "familia": {"n": (12, 25), "pref": {"Lácteos y huevos": 2, "Despensa": 2, "Panadería": 1.5, "Limpieza": 1.5}},
    "pareja": {"n": (8, 16), "pref": {"Fruta y verdura": 1.5, "Bebidas": 1.3, "Listos para comer": 1.2}},
    "estudiante": {"n": (4, 10), "pref": {"Listos para comer": 3, "Despensa": 1.5, "Bebidas": 2}},
    "fitness": {"n": (6, 14), "pref": {"Carne": 2.5, "Fruta y verdura": 2, "Lácteos y huevos": 2}},
    "vegano": {"n": (6, 14), "pref": {"Fruta y verdura": 3, "Despensa": 2}},
    "senior": {"n": (5, 12), "pref": {"Fruta y verdura": 2, "Pescado": 2, "Panadería": 1.5}},
}

STORES = [  # ficticias
    ("T01", "Tienda Benimaclet", "Valencia", 1.20), ("T02", "Tienda Campus Vera", "Valencia", 1.00),
    ("T03", "Tienda Ruzafa", "Valencia", 1.10), ("T04", "Tienda Albaida", "Albaida", 0.55),
    ("T05", "Tienda Orihuela Centro", "Orihuela", 0.75),
]

START, END = date(2024, 10, 1), date(2026, 9, 30)
DOW = [0.85, 0.85, 0.90, 0.95, 1.15, 1.35, 0.0]


def season_factor(kind: str, d: date) -> float:
    doy = d.timetuple().tm_yday
    if kind == "verano":
        return max(0.25, 1 + 0.8 * math.cos(2 * math.pi * (doy - 200) / 365))
    if kind == "invierno":
        return max(0.3, 1 + 0.6 * math.cos(2 * math.pi * (doy - 15) / 365))
    if kind == "navidad":
        return 6.0 if is_christmas_season(d) else 0.25
    if kind == "navidad_suave":
        return 1.8 if is_christmas_season(d) else 1.0
    if kind == "fallas":
        return 15.0 if is_fallas(d) else (2.0 if d.month in (10, 11) else 0.3)  # buñuelos: Fallas y Todos los Santos
    return 1.0


def build_catalog(rng: np.random.Generator) -> pd.DataFrame:
    rows, pid = [], 1
    for (key, name, sec, cat, w, price, kcal, prot, hc, fat, alg, tags, season, demand) in BASE:
        brands = BRANDS.get(sec, ["Hacendado"])
        variants = [(brands[0], w, price, "")]
        if sec not in ("Fruta y verdura", "Carne", "Pescado") and w < 3000:
            variants.append((brands[0], w * 2, round(price * 1.85, 2), " (formato ahorro)"))
        if len(brands) > 1:
            variants.append((brands[1], w, round(price * rng.uniform(0.95, 1.25), 2), ""))
        for i, (brand, ww, pp, suffix) in enumerate(variants):
            rows.append({
                "id": f"P{pid:04d}", "clave": key, "nombre": f"{name}{suffix}", "marca": brand, "seccion": sec,
                "categoria": cat, "peso_g": ww, "precio": pp, "precio_kg": round(pp / ww * 1000, 2),
                "kcal_100g": kcal, "proteinas_100g": prot, "hidratos_100g": hc, "grasas_100g": fat,
                "alergenos": alg, "trazas": TRAZAS.get(key, ""), "etiquetas": tags, "temporada": season,
                "demanda_base": demand if i == 0 else max(1, round(demand * 0.35)),
            })
            pid += 1
    return pd.DataFrame(rows)


def build_sales(rng: np.random.Generator, cat: pd.DataFrame) -> pd.DataFrame:
    main = cat.drop_duplicates("clave").sort_values("demanda_base", ascending=False)
    chosen = pd.concat([main.head(45), main[main.temporada.isin(["verano", "invierno", "navidad", "fallas"])]]).drop_duplicates("id")
    days = pd.date_range(START, END, freq="D").date
    out = []
    for _, p in chosen.iterrows():
        for sid, _, _, sfac in STORES:
            base = p.demanda_base * sfac
            lam = []
            for d in days:
                if is_closed(d):
                    lam.append(0.0)
                    continue
                f = DOW[d.weekday()] * season_factor(p.temporada, d) * (1 + 0.05 * (d - START).days / 365)
                if is_pre_holiday(d):
                    f *= 1.35
                lam.append(base * f * rng.lognormal(0, 0.08))
            units = rng.poisson(np.array(lam))
            out.append(pd.DataFrame({"fecha": days, "tienda_id": sid, "producto_id": p.id, "unidades": units}))
    return pd.concat(out, ignore_index=True)


def build_customers(rng: np.random.Generator) -> pd.DataFrame:
    profs = list(PROFILES)
    return pd.DataFrame({
        "cliente_id": [f"C{i:04d}" for i in range(1, 401)],
        "perfil": rng.choice(profs, 400, p=[0.3, 0.2, 0.15, 0.12, 0.08, 0.15]),
        "tienda_habitual": rng.choice([s[0] for s in STORES], 400),
        "personas_hogar": rng.integers(1, 6, 400),
    })


def build_tickets(rng: np.random.Generator, cat: pd.DataFrame, cust: pd.DataFrame, n_tickets: int = 12000) -> pd.DataFrame:
    by_key = cat.groupby("clave")["id"].apply(list).to_dict()
    lines = []
    open_days = [d for d in pd.date_range(START, END).date if not is_closed(d)]
    for t in range(n_tickets):
        c = cust.iloc[rng.integers(len(cust))]
        prof = PROFILES[c.perfil]
        pool = cat if c.perfil != "vegano" else cat[cat.etiquetas.str.contains("vegano") | cat.etiquetas.str.contains("no_alimentacion")]
        w = pool.seccion.map(lambda s: prof["pref"].get(s, 1.0)).to_numpy() * pool.demanda_base.to_numpy()
        n = max(2, rng.integers(*prof["n"]) // 2)
        items = set(rng.choice(pool.id.to_numpy(), size=min(n, len(pool)), replace=False, p=w / w.sum()))
        for _ in range(rng.integers(1, 3)):
            if rng.random() < 0.8:
                bundle = BUNDLES[rng.integers(len(BUNDLES))]
                for k in bundle:
                    if rng.random() < 0.85 and k in by_key:
                        items.add(by_key[k][0] if rng.random() < 0.8 else rng.choice(by_key[k]))
        d = open_days[rng.integers(len(open_days))]
        for pid in items:
            lines.append((f"K{t:06d}", c.cliente_id, c.tienda_habitual, d, pid, int(rng.integers(1, 3))))
    return pd.DataFrame(lines, columns=["ticket_id", "cliente_id", "tienda_id", "fecha", "producto_id", "cantidad"])


def main() -> None:
    rng = np.random.default_rng(SEED)
    out = settings.data_dir
    out.mkdir(parents=True, exist_ok=True)
    cat = build_catalog(rng)
    cat.to_csv(out / "catalogo.csv", index=False)
    pd.DataFrame(STORES, columns=["tienda_id", "nombre", "municipio", "factor_tamano"]).to_csv(out / "tiendas.csv", index=False)
    cust = build_customers(rng)
    cust.to_csv(out / "clientes.csv", index=False)
    sales = build_sales(rng, cat)
    sales.to_csv(out / "ventas.csv", index=False)
    tickets = build_tickets(rng, cat, cust)
    tickets.to_csv(out / "tickets.csv", index=False)
    print(f"Catálogo: {len(cat)} | Ventas: {len(sales):,} filas ({sales.producto_id.nunique()} productos) | "
          f"Tickets: {tickets.ticket_id.nunique():,} ({len(tickets):,} líneas) -> {out}")


if __name__ == "__main__":
    main()
