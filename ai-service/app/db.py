"""Base de datos de tickets (SQLAlchemy Core).

El esquema "oficial" para PostgreSQL está en db/schema.sql (es el contrato con Spring Boot / Spring Batch).
Aquí se define el mismo esquema para poder crearlo también en SQLite y desarrollar sin instalar nada.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text,
                        UniqueConstraint, create_engine, text)
from sqlalchemy.engine import Engine

from app.config import settings

metadata = MetaData()

productos = Table(
    "productos", metadata,
    Column("id", String(10), primary_key=True),
    Column("clave", String(40), nullable=False),          # producto "base" (agrupa formatos/marcas)
    Column("nombre", String(120), nullable=False),
    Column("marca", String(60)),
    Column("seccion", String(60), nullable=False),
    Column("categoria", String(60), nullable=False),
    Column("precio", Float, nullable=False),
    Column("formato_g", Integer),
    Column("alergenos", String(200), default=""),         # csv: gluten,lactosa,...
    Column("trazas", String(200), default=""),
    Column("etiquetas", String(200), default=""),         # csv: vegano,sin_gluten,fresco,...
    Column("envase", Text, default="[]"),                 # json: [["botella de plástico","amarillo"], ...]
    Column("sensible", Boolean, default=False),           # nunca aparece en recomendaciones ni en cestas
)

clientes = Table(
    "clientes", metadata,
    Column("id", String(20), primary_key=True),
    Column("nombre", String(80), nullable=False),
    Column("telefono", String(20), unique=True),
    Column("tarjeta_token", String(64), unique=True),     # identificador cifrado de la tarjeta, NUNCA el número
    Column("creado_en", DateTime, nullable=False),
)

preferencias = Table(
    "preferencias", metadata,
    Column("cliente_id", String(20), ForeignKey("clientes.id"), primary_key=True),
    Column("tipo", String(20), primary_key=True),         # interes | restriccion | alergia
    Column("valor", String(60), primary_key=True),
    Column("peso", Float, default=1.0),
    Column("origen", String(20), default="onboarding"),   # onboarding | chat | aprendido
)

tickets = Table(
    "tickets", metadata,
    Column("id", String(24), primary_key=True),
    Column("cliente_id", String(20), ForeignKey("clientes.id"), index=True),
    Column("tienda_id", String(10)),
    Column("fecha", DateTime, nullable=False, index=True),
    Column("total", Float, nullable=False),
    Column("metodo_pago", String(20)),                    # tarjeta | efectivo | online
    Column("origen", String(20)),                         # ticket_digital | foto | online | manual
    Column("hash_dedupe", String(64), unique=True),       # evita contar dos veces el mismo ticket
)

lineas_ticket = Table(
    "lineas_ticket", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticket_id", String(24), ForeignKey("tickets.id"), index=True, nullable=False),
    Column("producto_id", String(10), ForeignKey("productos.id"), index=True, nullable=False),
    Column("cantidad", Integer, nullable=False),
    Column("precio_unitario", Float, nullable=False),
)

feedback = Table(
    "feedback", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cliente_id", String(20), ForeignKey("clientes.id"), index=True),
    Column("producto_id", String(10), ForeignKey("productos.id")),
    Column("tipo", String(20)),                           # me_gusta | no_me_gusta | descartar
    Column("fecha", DateTime),
    UniqueConstraint("cliente_id", "producto_id", "tipo"),
)


@lru_cache(maxsize=1)
def engine() -> Engine:
    url = settings.database_url
    if url.startswith("sqlite"):
        from pathlib import Path
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, future=True)


def _crear_bd_si_falta() -> None:
    """En PostgreSQL, crea la base de datos (p. ej. mercadona_db) si aún no existe."""
    from sqlalchemy.engine import make_url
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        return
    servidor = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with servidor.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar():
            c.execute(text(f'CREATE DATABASE "{url.database}"'))
            print(f"Base de datos {url.database} creada")
    servidor.dispose()


def create_schema() -> None:
    _crear_bd_si_falta()
    metadata.create_all(engine())


def query_df(sql: str, **params) -> pd.DataFrame:
    with engine().connect() as c:
        df = pd.read_sql(text(sql), c, params=params)
    for col in df.columns:  # SQLite devuelve las fechas como texto
        if col == "fecha" or col.startswith("fecha_") or col == "creado_en":
            df[col] = pd.to_datetime(df[col])
    return df


def scalar(sql: str, **params):
    with engine().connect() as c:
        return c.execute(text(sql), params).scalar()
