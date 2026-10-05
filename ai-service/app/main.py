"""Servicio de IA (FastAPI). Lo consume el backend Spring Boot por REST.

  uvicorn app.main:app --reload --port 8001        -> docs interactivas en http://localhost:8001/docs
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import insert, select

from app import db, trazas
from app.agent.tools import agent
from app.cesta import cesta as cesta_mod
from app.config import ROOT, settings
from app.data import catalogo
from app.llm.gateway import gateway
from app.perfil import perfil
from app.perfil.intereses import ALERGENOS, RESTRICCIONES, tarjetas_onboarding
from app.recsys.recommender import recargar as recargar_modelo
from app.recsys.recommender import recomendar
from app.reciclaje import reciclaje

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = FastAPI(title="Servicio de IA – asistente de compra", version="1.0",
              description="Recomendaciones adaptativas, asistente conversacional, cesta con presupuesto y reciclaje sobre los tickets digitales.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
if trazas.ACTIVAS:
    logging.getLogger("uvicorn.access").disabled = True  # ya imprimimos cada petición con más detalle

SIN_TRAZA = ("/health", "/docs", "/openapi.json", "/redoc", "/favicon")


@app.middleware("http")
async def traza_peticiones(request, call_next):
    """Cada petición de la app sale en la consola como un bloque con lo que ha pasado dentro."""
    ruta = request.url.path
    estatica = ruta == "/" or "." in ruta.rsplit("/", 1)[-1] or ruta.startswith(SIN_TRAZA)
    if estatica or request.method == "OPTIONS":
        return await call_next(request)
    token, t0, estado = trazas.empezar(), time.perf_counter(), 500
    try:
        response = await call_next(request)
        estado = response.status_code
        return response
    finally:
        q = request.url.query
        trazas.terminar(token, request.method, ruta + (f"?{q}" if q else ""), estado, int((time.perf_counter() - t0) * 1000))


# ------------------------------------------------------------------ modelos
class CuentaIn(BaseModel):
    nombre: str
    telefono: str
    intereses: list[str] = Field(description="ids de /onboarding/intereses")
    restricciones: list[str] = []
    alergias: list[str] = []


class LoginIn(BaseModel):
    telefono: str | None = None
    tarjeta_token: str | None = None


class LineaIn(BaseModel):
    producto_id: str
    cantidad: int = 1
    precio_unitario: float | None = None


class TicketIn(BaseModel):
    """Ticket digital tal como lo entregaría Spring Batch (o una foto/entrada manual de un pago en efectivo)."""
    cliente_id: str | None = None
    telefono: str | None = None
    tarjeta_token: str | None = None
    tienda_id: str = "T01"
    fecha: datetime | None = None
    metodo_pago: str = "tarjeta"
    origen: str = "ticket_digital"
    lineas: list[LineaIn]


class ChatIn(BaseModel):
    mensaje: str


class CestaIn(BaseModel):
    presupuesto: float
    personas: int | None = None
    restricciones: list[str] = []
    alergias: list[str] = []
    variante: int = 0


class GustosIn(BaseModel):
    me_gusta: list[str] = []
    no_me_gusta: list[str] = []


def _cliente(cliente_id: str) -> dict:
    c = perfil.obtener(cliente_id)
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return c


# ------------------------------------------------------------------ sistema
@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/config")
def config() -> dict:
    from app.recsys.recommender import embeddings
    return {"proveedores_configurados": settings.providers, "proveedores_disponibles": gateway.available_providers(),
            "modelo_local": settings.ollama_model, "modo_llm": settings.llm_mode,
            "base_de_datos": settings.database_url.split("://")[0], "recomendador": embeddings()[3]}


@app.get("/stats")
def stats() -> dict:
    return gateway.stats


# ------------------------------------------------------------------ cuenta y onboarding
@app.get("/onboarding/intereses")
def intereses() -> dict:
    """Tarjetas tipo Pinterest para el alta + restricciones y alérgenos disponibles."""
    return {"intereses": tarjetas_onboarding(catalogo.df()),
            "restricciones": [{"id": k, "titulo": v["titulo"]} for k, v in RESTRICCIONES.items()],
            "alergenos": ALERGENOS}


@app.post("/clientes")
def crear_cuenta(body: CuentaIn) -> dict:
    try:
        c = perfil.crear(body.nombre, body.telefono, body.intereses, body.restricciones, body.alergias)
    except ValueError as e:
        trazas.paso("ERROR", str(e))
        raise HTTPException(400, str(e))
    trazas.paso("GUARDADO", f"Cuenta {c['id']} ({c['nombre']}): {len(body.intereses)} gustos, "
                            f"{len(body.restricciones)} dietas, {len(body.alergias)} alergias")
    trazas.paso("RESULTADO", "Sin compras todavía: sus recomendaciones saldrán de los gustos elegidos")
    return c


@app.post("/clientes/login")
def login(body: LoginIn) -> dict:
    c = perfil.identificar(body.telefono, body.tarjeta_token)
    if not c:
        trazas.paso("BD", "Ninguna cuenta con ese teléfono o tarjeta")
        raise HTTPException(404, "No hay ninguna cuenta con ese teléfono o tarjeta")
    trazas.paso("BD", f"Cliente encontrado: {c['id']} ({c['nombre']})")
    return c


@app.get("/clientes/{cliente_id}/perfil")
def ver_perfil(cliente_id: str) -> dict:
    """Pantalla 'Esto es lo que sé de ti': transparencia total."""
    c = _cliente(cliente_id)
    n = db.scalar("SELECT COUNT(*) FROM tickets WHERE cliente_id = :c", c=cliente_id)
    prefs = perfil.preferencias(cliente_id)
    trazas.paso("BD", f"Perfil de {cliente_id}: {len(prefs['intereses'])} gustos, {len(prefs['restricciones']) + len(prefs['alergias'])} "
                      f"restricciones, {len(prefs['no_me_gusta'])} descartados, {n} tickets")
    return {**c, "preferencias": prefs, "tickets_guardados": n}


@app.post("/clientes/{cliente_id}/gustos")
def gustos(cliente_id: str, body: GustosIn) -> dict:
    _cliente(cliente_id)
    return perfil.actualizar_gustos(cliente_id, body.me_gusta, body.no_me_gusta)


# ------------------------------------------------------------------ tickets
@app.post("/tickets")
def ingerir_ticket(body: TicketIn) -> dict:
    """Ingesta de un ticket. En producción Spring Batch escribe directamente en PostgreSQL;
    este endpoint sirve para la demo y para tickets de pagos en efectivo (foto o entrada manual)."""
    c = perfil.obtener(body.cliente_id) if body.cliente_id else perfil.identificar(body.telefono, body.tarjeta_token)
    if not c:
        raise HTTPException(404, "Ticket sin cliente asociado (teléfono o tarjeta desconocidos)")
    cat = catalogo.df()
    for li in body.lineas:
        if li.producto_id not in cat.index:
            raise HTTPException(400, f"Producto desconocido: {li.producto_id}")
    fecha = body.fecha or datetime.now()
    lineas = [{"producto_id": li.producto_id, "cantidad": li.cantidad,
               "precio_unitario": li.precio_unitario if li.precio_unitario is not None else float(cat.loc[li.producto_id, "precio"])}
              for li in body.lineas]
    total = round(sum(li["cantidad"] * li["precio_unitario"] for li in lineas), 2)
    trazas.paso("TICKET", f"De {c['id']} ({c['nombre']}): {len(lineas)} productos, {total:.2f} €, pago {body.metodo_pago}, origen {body.origen}")
    # deduplicado: mismo cliente, tienda, minuto e importe = mismo ticket (tarjeta + foto del mismo ticket)
    h = hashlib.sha256(f"{c['id']}|{body.tienda_id}|{fecha:%Y-%m-%d %H:%M}|{total:.2f}".encode()).hexdigest()
    with db.engine().begin() as conn:
        if conn.execute(select(db.tickets.c.id).where(db.tickets.c.hash_dedupe == h)).first():
            trazas.paso("DEDUPLICADO", "Ya estaba registrado (mismo cliente, tienda, minuto e importe): no se guarda dos veces")
            return {"duplicado": True, "mensaje": "Este ticket ya estaba registrado"}
        tid = f"W{datetime.now():%y%m%d%H%M%S%f}"[:24]
        conn.execute(insert(db.tickets).values(id=tid, cliente_id=c["id"], tienda_id=body.tienda_id, fecha=fecha, total=total,
                                               metodo_pago=body.metodo_pago, origen=body.origen, hash_dedupe=h))
        conn.execute(insert(db.lineas_ticket), [{"ticket_id": tid, **li} for li in lineas])
    trazas.paso("GUARDADO", f"Ticket {tid} guardado en tickets + lineas_ticket")
    trazas.paso("RESULTADO", "Las próximas recomendaciones ya cuentan con esta compra")
    return {"duplicado": False, "ticket_id": tid, "cliente_id": c["id"], "total": total,
            "reciclaje": reciclaje.resumen_ticket(tid)}


# ------------------------------------------------------------------ IA
@app.get("/clientes/{cliente_id}/recomendaciones")
def recomendaciones(cliente_id: str, n: int = 6) -> dict:
    _cliente(cliente_id)
    return recomendar(cliente_id, n)


@app.post("/clientes/{cliente_id}/chat")
def chat(cliente_id: str, body: ChatIn) -> dict:
    _cliente(cliente_id)
    try:
        return agent.run(cliente_id, body.mensaje)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/clientes/{cliente_id}/chat/reset")
def chat_reset(cliente_id: str) -> dict:
    agent.reset(cliente_id)
    return {"ok": True}


@app.post("/clientes/{cliente_id}/cesta")
def cesta(cliente_id: str, body: CestaIn) -> dict:
    """Dona llena la cesta (lo mismo que hace el chat, pero directo: para "Otra propuesta")."""
    _cliente(cliente_id)
    r = cesta_mod.preparar(cliente_id, body.presupuesto, body.personas, body.restricciones, body.alergias, body.variante)
    if "error" in r:
        raise HTTPException(400, r["error"])
    return r


@app.get("/clientes/{cliente_id}/reciclaje")
def ver_reciclaje(cliente_id: str, ticket_id: str | None = None) -> dict:
    _cliente(cliente_id)
    if ticket_id:
        return reciclaje.resumen_ticket(ticket_id)
    from app.config import hoy
    from datetime import timedelta
    return reciclaje.resumen_cliente(cliente_id, hoy() - timedelta(days=30), hoy() + timedelta(days=1))


@app.get("/productos")
def productos(q: str, limite: int = 10) -> dict:
    return {"productos": catalogo.buscar(q, limite)}


@app.get("/productos/{producto_id}/reciclaje")
def reciclaje_producto(producto_id: str) -> dict:
    if producto_id not in catalogo.df().index:
        raise HTTPException(404, "Producto no encontrado")
    p = catalogo.producto(producto_id)
    return reciclaje.donde_tiro({**p, "envase": catalogo.df().loc[producto_id, "envase"]})


@app.post("/admin/recargar-modelo")
def recargar() -> dict:
    """Lo llamaría el job nocturno de Spring Batch tras reentrenar los embeddings."""
    recargar_modelo()
    catalogo.recargar()
    return {"ok": True}


# ------------------------------------------------------------------ modo "sin backend Java"
# Las mismas rutas /api que expone Spring Boot, para que la app funcione también solo con Python
# (plan B en la demo). En el despliegue normal, la app habla con Spring (puerto 8080).
api = APIRouter(prefix="/api", tags=["modo sin backend Java"])


@api.get("/status")
def api_status() -> dict:
    return {"status": "Servicio de IA operativo (modo sin backend Java)"}


@api.get("/ia/estado")
def api_estado() -> dict:
    return config()


@api.get("/onboarding/intereses")
def api_intereses() -> dict:
    return intereses()


@api.post("/clientes", status_code=201)
def api_crear(body: CuentaIn) -> dict:
    return crear_cuenta(body)


@api.post("/clientes/login")
def api_login(body: LoginIn) -> dict:
    return login(body)


@api.get("/productos")
def api_productos(q: str = "") -> list:
    r = catalogo.buscar(q, 20) if q.strip() else []
    trazas.paso("BD", f"Catálogo: «{q}» -> {len(r)} productos" + (f" ({', '.join(p['nombre'] for p in r[:3])}...)" if r else ""))
    return r


@api.get("/clientes/{cliente_id}/perfil")
def api_perfil(cliente_id: str) -> dict:
    return ver_perfil(cliente_id)


@api.get("/clientes/{cliente_id}/recomendaciones")
def api_recomendaciones(cliente_id: str, n: int = 6) -> dict:
    return recomendaciones(cliente_id, n)


@api.post("/clientes/{cliente_id}/chat")
def api_chat(cliente_id: str, body: ChatIn) -> dict:
    return chat(cliente_id, body)


@api.post("/clientes/{cliente_id}/chat/reset")
def api_chat_reset(cliente_id: str) -> dict:
    return chat_reset(cliente_id)


@api.post("/clientes/{cliente_id}/gustos")
def api_gustos(cliente_id: str, body: GustosIn) -> dict:
    return gustos(cliente_id, body)


@api.post("/clientes/{cliente_id}/cesta")
def api_cesta(cliente_id: str, body: CestaIn) -> dict:
    return cesta(cliente_id, body)


@api.get("/clientes/{cliente_id}/reciclaje")
def api_reciclaje(cliente_id: str, ticket_id: str | None = None) -> dict:
    return ver_reciclaje(cliente_id, ticket_id)


@api.post("/tickets", status_code=201)
def api_ticket(body: TicketIn) -> dict:
    return ingerir_ticket(body)


@api.get("/clientes/{cliente_id}/tickets")
def api_tickets(cliente_id: str, limite: int = 5) -> list:
    _cliente(cliente_id)
    t = db.query_df("SELECT id, fecha, tienda_id, total, metodo_pago, origen FROM tickets WHERE cliente_id = :c "
                    "ORDER BY fecha DESC LIMIT :n", c=cliente_id, n=min(max(limite, 1), 20))
    out = []
    for r in t.itertuples():
        lin = db.query_df("""SELECT l.producto_id, p.nombre, l.cantidad, l.precio_unitario FROM lineas_ticket l
                             JOIN productos p ON p.id = l.producto_id WHERE l.ticket_id = :t AND p.sensible = :f""", t=r.id, f=False)
        out.append({"id": r.id, "fecha": r.fecha.isoformat(), "tienda_id": r.tienda_id, "total": float(r.total),
                    "metodo_pago": r.metodo_pago, "origen": r.origen, "lineas": lin.to_dict(orient="records")})
    trazas.paso("BD", f"Últimos {len(out)} tickets de {cliente_id}")
    return out


app.include_router(api)

# La app web (frontend/index.html) también se sirve desde aquí: http://localhost:8001/
FRONTEND = ROOT.parent / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


def _banner() -> None:
    if not trazas.ACTIVAS:
        return
    disp = [p for p in gateway.available_providers() if p != "mock"]
    linea = trazas._c("verde", "=" * trazas.ANCHO)
    print("\n".join([
        "", linea,
        "  " + trazas._c("verde", "DONA, no te abandona", True) + trazas._c("gris", "   -   servicio de IA listo"),
        linea,
        "  App web ........ " + trazas._c("", "http://localhost:8001", True) + trazas._c("gris", "   (o http://localhost:8080 con Spring)"),
        "  Modelo ......... " + (trazas._c("magenta", ", ".join(disp)) if disp else trazas._c("amarillo", "ninguno: modo demo sin LLM")),
        "  Base de datos .. " + settings.database_url.split("://")[0] + "   |   Recomendador: " + __import__("app.recsys.recommender", fromlist=["x"]).embeddings()[3],
        "  " + trazas._c("gris", "Usa la app en el navegador: aquí verás todo lo que pasa por dentro."),
        linea,
    ]), flush=True)


try:
    _banner()
except Exception as e:  # sin base de datos todavía (antes del seed): que no impida arrancar
    print(f"Aviso: {e}")
