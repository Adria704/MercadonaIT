# Arquitectura y por qué de cada tecnología

## Visión general

```
                 ┌──────────────────────────────┐
  Cliente  ───►  │  App web de Dona (HTML + JS)  │  alta tipo Pinterest, inicio, chat, cesta
                 └──────────────┬───────────────┘
                                │ REST
                 ┌──────────────▼───────────────┐
                 │  Backend Java + Spring Boot 4 │  cuentas, tickets, API pública, orquesta
                 └───────┬──────────────┬───────┘
                         │ REST         │ JPA
          ┌──────────────▼───┐   ┌──────▼──────────────────────┐
          │ Servicio de IA    │   │ PostgreSQL                  │
          │ Python (FastAPI)  │◄──┤ tickets, líneas, productos, │
          │ + PyTorch + LLM   │   │ clientes, preferencias      │
          └────────┬─────────┘   └──────▲──────────────────────┘
                   │                    │ escribe por lotes
          ┌────────▼─────────┐   ┌──────┴──────────────────────┐
          │ Qwen 2.5 7B local │   │ Ingesta del ticket digital  │
          │ (Ollama) o API    │   │ hoy: POST /api/tickets      │
          │ gratuita          │   │ siguiente: Spring Batch     │
          └──────────────────┘   └─────────────────────────────┘
```

**Flujo:** el cliente paga → se genera el ticket digital asociado a su tarjeta o teléfono → el backend lo valida, deduplica y lo guarda en PostgreSQL → el servicio de IA lo usa para las recomendaciones, el asistente y las cestas → el backend lo expone al frontend. El frontend **solo habla con el backend** (puerto 8080); el backend reenvía las peticiones de IA al servicio Python (puerto 8001).

## Por qué cada tecnología

### Frontend: app web ligera (HTML + JavaScript)
- Un único fichero sin paso de compilación: se abre en cualquier móvil o portátil y lo sirve el propio backend (`http://localhost:8080`), así que no hay CORS ni otro servidor que arrancar.
- Diseño *mobile-first* con identidad propia (Dona) y accesible: tamaños táctiles de 44 px, modo oscuro y movimiento reducido.
- Toda la comunicación pasa por una capa `api` de 12 funciones; migrar a **React** consiste en mover cada pantalla a un componente sin tocar el backend.

### Backend: Java 17 + Spring Boot 4
- **Spring Boot** es el estándar en backends empresariales de la JVM: acceso a datos con JPA, seguridad (Spring Security para las cuentas), configuración y despliegue maduros.
- **Java 17** (LTS): el lenguaje más extendido en backends corporativos, con *records*, *pattern matching* y un ecosistema enorme. *Kotlin* sería una alternativa natural (menos código, *null-safety*, el lenguaje de Android) y convive con Java en el mismo proyecto si se quiere migrar poco a poco.
- Responsabilidades: cuentas y alta (onboarding), ingesta de tickets con deduplicado, catálogo, y ser la única puerta de entrada del frontend, incluido el reenvío al servicio de IA.

### Ingesta del ticket digital (y Spring Batch como siguiente paso)
- Hoy, cada ticket entra por `POST /api/tickets`: el backend identifica al cliente por teléfono o token de tarjeta, calcula el total, **deduplica** (mismo cliente + tienda + minuto + importe = mismo ticket, por ejemplo tarjeta + foto del mismo ticket) y lo guarda línea a línea.
- En producción los tickets llegan en volumen, así que es un problema de **procesamiento por lotes**: **Spring Batch** aportaría lectura por *chunks*, reintentos, reanudación si un job falla a mitad y trazabilidad. Jobs previstos: ingesta masiva, y reentrenar los embeddings por la noche (avisando después a `/admin/recargar-modelo`).

### Base de datos: PostgreSQL
- Los tickets son datos **relacionales** por naturaleza: cliente → tickets → líneas → productos. Las consultas sobre el historial (gasto por sección, cada cuánto se compra cada producto) son SQL puro.
- Transacciones ACID: un ticket se guarda entero o no se guarda.
- `JSONB` para datos flexibles (componentes del envase para reciclaje) sin perder el modelo relacional.
- Escala de sobra y, si hiciera falta búsqueda vectorial, la extensión `pgvector` permite guardar los embeddings en la misma base de datos.
- En desarrollo usamos SQLite con el **mismo esquema** (`db/schema.sql`) para arrancar sin instalar nada.

### Servicio de IA: Python
- Es el lenguaje del ecosistema de IA (PyTorch, pandas, numpy, clientes de LLM). Separarlo en un microservicio permite que el equipo de backend y el de IA trabajen en paralelo con un contrato REST claro (FastAPI genera la documentación OpenAPI en `/docs`).

### Modelo de recomendación: PyTorch
- Entrenamos **embeddings de producto (item2vec)**: una red que aprende, a partir de qué productos aparecen juntos en los tickets, un vector por producto. Productos que se compran juntos acaban cerca ("arroz" cerca de "pollo", "colorante de paella", "judía verde").
- Con esos vectores representamos también al cliente. Los gustos elegidos en el onboarding y sus compras viven **en el mismo espacio**, y eso es lo que permite la adaptación progresiva.
- PyTorch solo se usa para **entrenar** (job nocturno). Para servir basta numpy: el servicio es ligero y rápido.

### LLM: Qwen 2.5 7B en local (Ollama), con API gratuita de respaldo
- **Local**: los datos de compra no salen de la máquina (privacidad), coste cero por consulta y funciona sin internet.
- **Qwen 2.5 7B**: buen español, soporta *tool calling* (necesario para que el asistente consulte los datos) y cabe en un portátil.
- **API gratuita (Gemini o Groq)** como respaldo automático, para que cualquiera pueda ejecutar el proyecto sin GPU ni Ollama.
- **Modo sin IA** al final de la cadena: la aplicación nunca muestra un error.

## Decisiones de diseño de la IA

1. **El LLM orquesta, el código calcula.** Cifras, fechas, aptitud de productos (alergias, vegano, sin gluten) y las cestas se calculan en código. El LLM solo decide qué herramienta usar y redacta. Así se evitan alucinaciones en lo importante.
2. **Adaptación progresiva:** `vector_cliente = (1 − α)·gustos_iniciales + α·compras`, con `α = tickets / (tickets + 8)`. Con la cuenta recién creada manda el onboarding; con 8 compras, mitad y mitad; con muchas, mandan las compras. Los intereses declarados siempre conservan un empujón mínimo.
3. **Siempre hay algo nuevo:** la lista "descubre" solo incluye productos nunca comprados, de categorías distintas y con un componente aleatorio diario.
4. **Explicable:** cada recomendación incluye su motivo ("porque sueles comprar X", "porque te interesa Vida fitness").
5. **Privacidad por diseño:** token de tarjeta en vez del número, productos sensibles excluidos de las recomendaciones y las cestas, y pantalla de transparencia (`/clientes/{id}/perfil`).

## Contrato entre componentes

| Quién | Escribe | Lee |
|---|---|---|
| Backend (Spring Boot) | `clientes`, `preferencias` (alta), `tickets`, `lineas_ticket` | `productos` y todo lo anterior |
| Servicio de IA | `feedback`, `preferencias` (aprendidas en el chat) | todo |
| `python -m app.data.seed` | crea el esquema (`ai-service/db/schema.sql`) y los datos de demo | — |

El backend usa `ddl-auto: none`: no modifica tablas compartidas. Si cambia el esquema, se cambia en `ai-service/app/db.py` y en `schema.sql`, y después en las entidades JPA.
