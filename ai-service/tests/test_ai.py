"""Tests sin red (proveedor mock) sobre una BD temporal. Ejecuta: python -m pytest -q"""
import os
import tempfile

os.environ["LLM_PROVIDERS"] = "mock"
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db").replace("\\", "/")

from app.data import seed  # noqa: E402

seed.main()

from fastapi.testclient import TestClient  # noqa: E402

from app.llm.gateway import OllamaProvider  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_ollama_conversion():
    msgs = [{"role": "user", "content": "hola"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "t", "arguments": {"a": 1}}]},
            {"role": "tool", "tool_call_id": "1", "name": "t", "content": "{}"}]
    out = OllamaProvider._convert(msgs, "sys")
    assert out[0]["role"] == "system" and out[2]["tool_calls"][0]["function"]["arguments"] == {"a": 1}
    assert out[3] == {"role": "tool", "content": "{}", "tool_name": "t"}


def test_onboarding_y_arranque_en_frio():
    tarjetas = client.get("/onboarding/intereses").json()["intereses"]
    assert len(tarjetas) >= 10
    c = client.post("/clientes", json={"nombre": "Test", "telefono": "699000000", "intereses": ["vegetal"],
                                       "restricciones": ["vegano"]}).json()
    r = client.get(f"/clientes/{c['id']}/recomendaciones").json()
    assert r["adaptacion"]["peso_compras"] == 0
    assert all("vegano" in p["etiquetas"] or p["seccion"] in ("Limpieza", "Higiene") for p in r["para_ti"] + r["descubre"])


def test_recomendaciones_se_adaptan():
    r = client.get("/clientes/C0001/recomendaciones").json()
    assert r["adaptacion"]["peso_compras"] > 0.8 and r["lo_de_siempre"] and r["descubre"]
    assert all(p["motivo"] for p in r["para_ti"])


def test_no_me_gusta_excluye():
    client.post("/clientes/C0002/gustos", json={"no_me_gusta": ["pizza"]})
    r = client.get("/clientes/C0002/recomendaciones").json()
    assert not any("Pizza" in p["nombre"] for p in r["para_ti"] + r["descubre"])


def test_wrapped_privacidad():
    w = client.get("/clientes/C0001/wrapped", params={"llm": False}).json()
    textos = " ".join(t["texto"] for t in w["compartible"]["tarjetas"])
    assert "€" not in textos and "Preservativos" not in str(w["estadisticas"])
    assert w["tarjeta_privada"]["texto"].count("€") == 1


def test_marcas_mercadona():
    marcas = {p["marca"] for q in ("leche", "champú", "detergente", "plátano") for p in client.get("/productos", params={"q": q}).json()["productos"]}
    assert {"Hacendado", "Deliplus", "Bosque Verde"} <= marcas and "Casa Clara" not in marcas


def test_ticket_y_duplicado_y_reciclaje():
    pid = client.get("/productos", params={"q": "leche semidesnatada"}).json()["productos"][0]["id"]
    body = {"telefono": "600111222", "fecha": "2026-10-02T18:30:00", "metodo_pago": "efectivo", "origen": "foto",
            "lineas": [{"producto_id": pid, "cantidad": 2}]}
    r1 = client.post("/tickets", json=body).json()
    assert not r1["duplicado"] and r1["reciclaje"]["por_contenedor"]
    assert client.post("/tickets", json=body).json()["duplicado"]


def test_chat():
    r = client.post("/clientes/C0001/chat", json={"mensaje": "¿Cuándo compré café la última vez?"}).json()
    assert r["traza"][0]["nombre"] == "historial_producto"


def test_cesta_respeta_presupuesto_y_dietas():
    r = client.post("/clientes/C0001/cesta", json={"presupuesto": 30, "personas": 3, "restricciones": ["sin_gluten", "vegano"]}).json()
    c = r["cesta"]
    assert 0 < c["total"] <= 30 and c["lineas"]
    for l in c["lineas"]:
        p = client.get("/productos", params={"q": l["nombre"]}).json()["productos"][0]
        assert "vegano" in p["etiquetas"] and "sin_gluten" in p["etiquetas"], l["nombre"]
    otra = client.post("/clientes/C0001/cesta", json={"presupuesto": 30, "personas": 3, "variante": 1}).json()["cesta"]
    assert otra["variante"] == 1


def test_chat_prepara_cesta():
    r = client.post("/clientes/C0002/chat", json={"mensaje": "20 € para dos, una vegetariana"}).json()
    paso = next(t for t in r["traza"] if t["tipo"] == "herramienta")
    assert paso["nombre"] == "preparar_cesta" and paso["cesta"]["total"] <= 20
    assert "vegetariano" in paso["cesta"]["restricciones"]


def test_rutas_api_modo_sin_java():
    assert client.post("/api/clientes/login", json={"telefono": "600111222"}).json()["id"] == "C0001"
    assert isinstance(client.get("/api/productos", params={"q": "leche"}).json(), list)
    assert client.get("/api/clientes/C0001/tickets").json()[0]["lineas"]
    r = client.post("/api/tickets", json={"cliente_id": "C0003", "origen": "online", "lineas": [{"producto_id": "P0001", "cantidad": 1}]})
    assert r.status_code == 201
