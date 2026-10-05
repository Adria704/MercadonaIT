"""Festivos nacionales + Comunitat Valenciana y helpers de calendario.

Se usan en el generador sintético y como features del forecast.
(Los domingos y festivos las tiendas están cerradas en el dataset sintético.)
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def easter(year: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def holidays(year: int) -> frozenset[date]:
    e = easter(year)
    fixed = [(1, 1), (1, 6), (3, 19), (5, 1), (6, 24), (8, 15), (10, 9), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)]
    days = {date(year, m, d) for m, d in fixed}
    days |= {e - timedelta(days=2), e + timedelta(days=1)}  # Viernes Santo, Lunes de Pascua
    return frozenset(days)


def is_holiday(d: date) -> bool:
    return d in holidays(d.year)


def is_closed(d: date) -> bool:
    return d.weekday() == 6 or is_holiday(d)


def is_pre_holiday(d: date) -> bool:
    """Último día abierto antes de un festivo (efecto 'víspera'). El sábado normal ya va en el día de la semana."""
    if is_closed(d):
        return False
    nxt = d + timedelta(days=1)
    if is_holiday(nxt):
        return True
    return d.weekday() == 5 and is_holiday(d + timedelta(days=2))  # sábado antes de lunes festivo


def is_fallas(d: date) -> bool:
    return d.month == 3 and 15 <= d.day <= 19


def is_christmas_season(d: date) -> bool:
    return (d.month == 12 and d.day >= 15) or (d.month == 1 and d.day <= 6)


FIXED_NAMES = {(1, 1): "Año Nuevo", (1, 6): "Reyes", (3, 19): "San José", (5, 1): "Día del Trabajo", (6, 24): "Sant Joan",
               (8, 15): "Asunción", (10, 9): "Día de la Comunitat Valenciana", (10, 12): "Fiesta Nacional",
               (11, 1): "Todos los Santos", (12, 6): "Día de la Constitución", (12, 8): "Inmaculada", (12, 25): "Navidad"}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def holiday_name(d: date) -> str | None:
    if (d.month, d.day) in FIXED_NAMES:
        return FIXED_NAMES[(d.month, d.day)]
    e = easter(d.year)
    if d == e - timedelta(days=2):
        return "Viernes Santo"
    if d == e + timedelta(days=1):
        return "Lunes de Pascua"
    return None


def fecha_texto(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def prev_open(d: date) -> date:
    while is_closed(d):
        d -= timedelta(days=1)
    return d


def next_open(d: date) -> date:
    while is_closed(d):
        d += timedelta(days=1)
    return d
