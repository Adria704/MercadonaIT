# Asistente de compra personal: hackathon Mercadona IT

Asistente que convierte el ticket digital en recomendaciones que se adaptan a ti, un chat con tus datos de compra, un "Wrapped" de tu año en el súper y consejos de reciclaje.

```
proyecto/
├── frontend/         App web de Dona (HTML + JavaScript, sin compilación) → la sirve el backend
├── backend/          Java 17 + Spring Boot 4  → API pública y app web (puerto 8080)
├── ai-service/       Python + FastAPI + PyTorch + LLM → servicio de IA (puerto 8001)
├── docs/             ARQUITECTURA.md: por qué cada tecnología y cómo encaja todo
├── docker-compose.yml   (opcional) PostgreSQL en Docker
└── arrancar.ps1      arranca IA y backend en dos ventanas (Windows)
```

| Pieza | Puerto | Quién la usa |
|---|---|---|
| PostgreSQL `mercadona_db` | 5432 | backend y servicio de IA (misma base de datos) |
| Servicio de IA | 8001 | solo el backend |
| Backend + app web | 8080 | el navegador: **http://localhost:8080** |

Los datos son **sintéticos**: el surtido usa las marcas de Mercadona (Hacendado, Deliplus, Bosque Verde), pero precios, tiendas y clientes son inventados.

## Instalación (una vez)

Requisitos: **Java 17+**, **Python 3.10+**, **PostgreSQL** con usuario `postgres` y clave `root` (o Docker) y, opcionalmente, **Ollama**.

**1. PostgreSQL.** Si ya lo tienes instalado con esas credenciales, no hay que hacer nada más (la base de datos se crea sola). Con Docker:

```powershell
docker compose up -d
```

**2. Servicio de IA** (crea la base de datos, las tablas y los datos de demo):

```powershell
cd ai-service
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.data.seed
cd ..
```

**3. Modelo de IA local (opcional, recomendado):** instala Ollama y ejecuta `ollama pull qwen2.5:7b`. Sin él, el servicio usa una API gratuita si pones su clave en `ai-service/.env` (`GEMINI_API_KEY` o `GROQ_API_KEY`), o un modo sin IA para que nada se caiga.

**4. Backend:** no hay que instalar nada; la primera vez `mvnw` descarga Maven y las dependencias.

## Arrancar (cada vez)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\arrancar.ps1
```

O a mano, en dos terminales:

```powershell
# Terminal 1: servicio de IA
cd ai-service; .\.venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --port 8001

# Terminal 2: backend
cd backend; .\mvnw.cmd spring-boot:run
```

Abre **http://localhost:8080**: es la app. Comprueba también http://localhost:8080/api/ia/estado (indica qué LLM se está usando).

**Plan B si el backend Java da problemas:** el servicio de IA también sirve la app y las mismas rutas `/api`. Arranca solo la IA y abre **http://localhost:8001**. Funciona igual (sin la parte Java).

## La app web (frontend/index.html)

Con la identidad de Dona ("Dona, no te abandona"):

- **Entrada:** teléfono o clientes de demo, y alta tipo Pinterest (gustos, dietas y alergias).
- **Inicio:** buscador y recomendaciones personalizadas (Para ti, Lo de siempre, Descubre), con el grado de adaptación.
- **Dona** (botón central): chat con la IA.
  - "30 € para una persona celíaca y dos veganas" → ticket con la cesta, con "Otra propuesta" y "Añadir a mi cesta".
  - Preguntas sobre tus compras.
  - Wrapped a pantalla completa.
- **Mi cesta** (arriba a la derecha): "Confirmar compra" la guarda como ticket digital, y Dona la tiene en cuenta en la siguiente recomendación.
- **Cuenta:** "Esto es lo que sé de ti", últimas compras y el Wrapped.
- **Categorías y Listas:** páginas vacías (fuera del alcance de la demo).

Para apuntar la app a otro servidor: `index.html?api=http://localhost:8080/api`.

## Probar sin frontend

- `backend/api.http`: todas las peticiones listas para lanzar desde IntelliJ (botón ▶) o VS Code (extensión REST Client).
- Desde PowerShell:

```powershell
Invoke-RestMethod http://localhost:8080/api/clientes/C0001/recomendaciones
Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/clientes/C0001/chat -ContentType "application/json" -Body '{"mensaje": "¿Cuánto llevo gastado este mes?"}'
```

- Chat por terminal directamente con la IA: `cd ai-service; python -m scripts.chat`

| Cliente de demo | Teléfono | Para enseñar |
|---|---|---|
| Laura (C0001) | 600111222 | 1 año de compras: recomendaciones basadas en su historial y Wrapped completo |
| Álex (C0002) | 600333444 | Estudiante: cocina rápida y aperitivo |
| Carmen (C0003) | 600555666 | Cuenta nueva, sin gluten: recomendaciones solo por sus gustos iniciales |

## API para el frontend (todo bajo `http://localhost:8080/api`)

| Método | Ruta | Qué hace | Lo resuelve |
|---|---|---|---|
| GET | `/status` | Backend operativo | Backend |
| GET | `/ia/estado` | LLM disponible (Qwen local, API gratuita o sin IA) | IA |
| GET | `/onboarding/intereses` | Tarjetas tipo Pinterest, restricciones y alérgenos | IA |
| POST | `/clientes` | Alta con intereses, restricciones y alergias | Backend |
| POST | `/clientes/login` | Identificar por teléfono o token de tarjeta | Backend |
| GET | `/clientes/{id}` | Datos básicos, preferencias y nº de tickets | Backend |
| GET | `/clientes/{id}/perfil` | "Esto es lo que sé de ti" (incluye gustos aprendidos) | IA |
| GET | `/productos?q=` | Buscar en el catálogo | Backend |
| POST | `/tickets` | Registrar un ticket digital (o de un pago en efectivo), con deduplicado | Backend |
| GET | `/clientes/{id}/tickets` | Últimos tickets con sus productos | Backend |
| POST | `/clientes/{id}/cesta` | Cesta de Dona: `{"presupuesto": 30, "personas": 3, "restricciones": ["sin_gluten"], "variante": 0}` | IA |
| GET | `/clientes/{id}/recomendaciones` | Lo de siempre, para ti y descubre, con motivo y grado de adaptación | IA |
| POST | `/clientes/{id}/chat` | Asistente: `{"mensaje": "..."}` | IA |
| POST | `/clientes/{id}/chat/reset` | Reiniciar la conversación | IA |
| POST | `/clientes/{id}/gustos` | `{"me_gusta": [...], "no_me_gusta": [...]}` | IA |
| GET | `/clientes/{id}/wrapped?periodo=2026` | Wrapped anual, mensual (`2026-09`) o del último año | IA |
| GET | `/clientes/{id}/reciclaje` | Envases por contenedor (30 días o `?ticket_id=`) | IA |
| GET | `/productos/{id}/reciclaje` | A qué contenedor va cada parte del envase | IA |

Todas las respuestas usan nombres de campo en `snake_case`. El frontend solo habla con el backend; el backend reenvía al servicio de IA.

## Guion de demo (90 s)

1. Entra como **Carmen** (cuenta nueva, sin gluten): sus recomendaciones salen solo de los gustos que eligió.
2. Botón **Dona** → "30 € para una persona celíaca y dos veganas" → ticket ajustado al euro y apto para todos. Pulsa "Otra propuesta".
3. "Añadir a mi cesta" → **Confirmar compra** → vuelve a Inicio: las recomendaciones ya mezclan gustos y compras.
4. Entra como **Laura** (1 año de compras) → "¿Cuánto llevo gastado este mes?" → "Enséñame mi Wrapped".

## Problemas frecuentes

- **`password authentication failed`**: la clave de PostgreSQL no es `root`. Cámbiala en `backend/src/main/resources/application.yml` **y** en `ai-service/.env`.
- **`relation "productos" does not exist`**: falta `python -m app.data.seed` en `ai-service`.
- **El chat responde "[modo demo sin LLM]"**: no hay Ollama con `qwen2.5:7b` ni clave de API gratuita. Mira `/api/ia/estado`.
- **`/api/...` de IA devuelve 503**: el servicio de IA no está arrancado en el puerto 8001.
- **`mvnw test` falla**: el test `contextLoads` necesita PostgreSQL en marcha.
