"""Evalúa si el asistente elige la herramienta correcta (precisión), con latencia por pregunta.

  python -m scripts.eval_agent       -> úsalo con Qwen local y con la API gratuita para comparar
"""
import time

from app.agent.tools import agent
from app.llm.gateway import gateway

CLIENTE = "C0001"
GOLDEN = [
    ("¿Qué me recomiendas para esta semana?", "recomendaciones"),
    ("Sorpréndeme con algo que no haya probado", "recomendaciones"),
    ("¿Cuánto llevo gastado este mes?", "resumen_compras"),
    ("¿Cuánto gasté en fruta y verdura este año?", "resumen_compras"),
    ("¿Cuándo fue la última vez que compré café?", "historial_producto"),
    ("¿Cada cuánto compro plátanos?", "historial_producto"),
    ("¿Qué compré en mi último ticket?", "ultimos_tickets"),
    ("Enséñame mi resumen del año", "mi_wrapped"),
    ("¿En qué contenedor tiro el brik de leche?", "reciclaje"),
    ("No me gusta nada el pescado", "actualizar_gustos"),
    ("¿Tenéis hummus?", "buscar_productos"),
]
ok = 0
for i, (q, esperado) in enumerate(GOLDEN):
    agent.reset(CLIENTE)
    t0 = time.perf_counter()
    r = agent.run(CLIENTE, q)
    tools = [t["nombre"] for t in r["traza"] if t["tipo"] == "herramienta"]
    hit = bool(tools) and tools[0] == esperado
    ok += hit
    print(f"{'OK ' if hit else 'MAL'} {q:<52} {str(tools[:2]):<45} {int((time.perf_counter() - t0) * 1000):>6} ms")
agent.reset(CLIENTE)
print(f"\nPrecisión de herramienta: {ok}/{len(GOLDEN)} = {ok / len(GOLDEN):.0%}")
print("Proveedores:", {k: v["calls"] for k, v in gateway.stats["by_provider"].items()})
if set(gateway.stats["by_provider"]) == {"mock"}:
    print("Aviso: se ha evaluado el modo sin LLM (palabras clave). Arranca Ollama o pon una API key gratuita.")
