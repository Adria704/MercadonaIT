# Servicio de IA: asistente de compra personal

Microservicio Python que pone la inteligencia sobre los tickets digitales:

- **Recomendaciones que se adaptan**: empiezan por lo que eliges al crear la cuenta (tarjetas tipo Pinterest) y van pasando a tus compras reales, sin dejar nunca de proponer cosas nuevas.
- **Asistente conversacional** con tus datos: "¿cuánto llevo gastado este mes?", "¿cuándo compré café?", "recomiéndame algo nuevo", "no me gusta el pescado", "30 € para dos, sin lactosa".
- **Cesta de Dona**: presupuesto + personas + dietas → cesta personalizada y apta para todos.
- **Reciclaje** (secundario): a qué contenedor va cada envase de tu compra.

El LLM corre **en local con Qwen 2.5 7B (Ollama)**; si no está disponible, usa una **API gratuita** (Gemini o Groq), y si tampoco hay, un modo sin IA para que nada se caiga.

## Arranque en Windows (PowerShell)

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.data.seed                    # datos sintéticos (~5 s)
python -m pytest -q                        # tests sin red (usan una BD temporal)
python -m uvicorn app.main:app --port 8001 # API en http://localhost:8001/docs
```

En macOS/Linux, lo mismo con `python3 -m venv .venv && source .venv/bin/activate`.

## El modelo de IA

**Local (recomendado):** instala [Ollama](https://ollama.com) y descarga el modelo una vez (unos 4,7 GB):

```powershell
ollama pull qwen2.5:7b
```

Con Ollama abierto, el servicio lo detecta solo (lo comprueba cada 30 s).

**API gratuita (para quien pruebe el proyecto sin Ollama):** pon una de estas claves en `.env`:

- `GEMINI_API_KEY`: gratis en https://aistudio.google.com
- `GROQ_API_KEY`: gratis en https://console.groq.com

Los planes gratuitos pueden usar los datos para mejorar sus modelos; por eso aquí solo hay datos sintéticos. En producción, el modelo correría en la infraestructura propia.

Comprueba qué está usando en `http://localhost:8001/config` (`proveedores_disponibles`).

## Probarlo sin frontend

```powershell
python -m scripts.chat               # chat por terminal como Laura (1 año de historial)
python -m scripts.chat 600555666     # como Carmen (cuenta nueva: solo gustos iniciales)
python -m scripts.eval_agent         # precisión eligiendo herramientas y latencia
```

| Cliente de demo | Teléfono | Para enseñar |
|---|---|---|
| Laura (C0001) | 600111222 | Recomendaciones basadas sobre todo en sus compras (94 %) y "Te toca reponer" |
| Álex (C0002) | 600333444 | Estudiante: cocina rápida y aperitivo, compra los viernes |
| Carmen (C0003) | 600555666 | Cuenta nueva: recomendaciones solo por sus gustos iniciales y sin gluten |

## Endpoints principales

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/onboarding/intereses` | Tarjetas tipo Pinterest, restricciones y alérgenos para el alta |
| POST | `/clientes` | Crear cuenta con intereses y restricciones |
| POST | `/clientes/login` | Identificar por teléfono o token de tarjeta |
| GET | `/clientes/{id}/perfil` | "Esto es lo que sé de ti" (transparencia) |
| POST | `/tickets` | Ingerir un ticket (Spring Batch, foto o pago en efectivo), con deduplicado |
| GET | `/clientes/{id}/recomendaciones` | Lo de siempre, para ti y descubre, con motivo y grado de adaptación |
| POST | `/clientes/{id}/chat` | Asistente conversacional con traza de herramientas |
| POST | `/clientes/{id}/gustos` | Me gusta / no me gusta |
| POST | `/clientes/{id}/cesta` | Cesta de Dona con presupuesto, personas y dietas |
| GET | `/clientes/{id}/reciclaje` | Envases por contenedor |

## Reentrenar el modelo de recomendación (PyTorch)

Los embeddings ya entrenados vienen en `models/`, así que el servicio **no necesita PyTorch** para funcionar. Para reentrenar:

```powershell
python -m pip install -r requirements-train.txt
python -m app.recsys.train
```

Si se borran los embeddings, el recomendador usa SVD sobre co-ocurrencias como respaldo.

## Base de datos

Por defecto usa **la misma PostgreSQL que el backend** (`mercadona_db`, usuario `postgres`, clave `root`). `python -m app.data.seed` crea la base de datos si no existe, el esquema y los datos de demo.

Para probar solo la IA sin PostgreSQL, deja `DATABASE_URL=` vacío en `.env` y usará SQLite.

Cómo se arranca todo junto: `README.md` de la raíz. Por qué cada tecnología: `docs/ARQUITECTURA.md`.
