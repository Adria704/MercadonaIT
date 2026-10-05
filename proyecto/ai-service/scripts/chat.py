"""Chat por terminal con el asistente (sin frontend).

  python -m scripts.chat               -> entra como Laura (600111222)
  python -m scripts.chat 600555666     -> entra como Carmen (cuenta nueva)
Comandos: /reset  /salir
"""
import sys

from app.agent.tools import agent
from app.llm.gateway import gateway
from app.perfil import perfil

tel = sys.argv[1] if len(sys.argv) > 1 else "600111222"
c = perfil.identificar(telefono=tel)
if not c:
    sys.exit(f"No existe ninguna cuenta con el teléfono {tel}. ¿Has ejecutado `python -m app.data.seed`?")
disp = [p for p in gateway.available_providers()]
print(f"Hola, {c['nombre']}. Proveedores disponibles: {', '.join(disp)}  (escribe /salir para terminar)\n")
while True:
    try:
        msg = input("Tú: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not msg:
        continue
    if msg == "/salir":
        break
    if msg == "/reset":
        agent.reset(c["id"])
        print("(conversación reiniciada)\n")
        continue
    r = agent.run(c["id"], msg)
    tools = [f"{t['nombre']}({t['argumentos']})" for t in r["traza"] if t["tipo"] == "herramienta"]
    print(f"\nAsistente: {r['respuesta']}")
    print(f"  [{', '.join(r['proveedores'])} | {r['ms_total']} ms | herramientas: {'; '.join(tools) or '—'}]\n")
