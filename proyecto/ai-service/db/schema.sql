-- Esquema PostgreSQL de tickets (contrato entre el backend Spring Boot y el servicio de IA).
-- Lo crea `python -m app.data.seed` (SQLAlchemy, mismos tipos). El backend usa ddl-auto: none y solo lo lee/escribe.
-- Spring Boot escribe clientes, preferencias (alta) y tickets/lineas_ticket (ingesta del ticket digital);
-- el servicio de IA lee todo y escribe feedback/preferencias aprendidas.

CREATE TABLE IF NOT EXISTS productos (
    id          VARCHAR(10) PRIMARY KEY,
    clave       VARCHAR(40)  NOT NULL,
    nombre      VARCHAR(120) NOT NULL,
    marca       VARCHAR(60),
    seccion     VARCHAR(60)  NOT NULL,
    categoria   VARCHAR(60)  NOT NULL,
    precio      DOUBLE PRECISION NOT NULL,
    formato_g   INTEGER,
    alergenos   VARCHAR(200) DEFAULT '',
    trazas      VARCHAR(200) DEFAULT '',
    etiquetas   VARCHAR(200) DEFAULT '',
    envase      TEXT         DEFAULT '[]',      -- JSON: [["botella de plástico","amarillo"], ...]
    sensible    BOOLEAN      DEFAULT FALSE      -- excluido del Wrapped y de recomendaciones
);

CREATE TABLE IF NOT EXISTS clientes (
    id             VARCHAR(20) PRIMARY KEY,
    nombre         VARCHAR(80) NOT NULL,
    telefono       VARCHAR(20) UNIQUE,
    tarjeta_token  VARCHAR(64) UNIQUE,          -- token cifrado de la tarjeta, nunca el número
    creado_en      TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS preferencias (
    cliente_id  VARCHAR(20) REFERENCES clientes(id) ON DELETE CASCADE,
    tipo        VARCHAR(20) NOT NULL,           -- interes | restriccion | alergia
    valor       VARCHAR(60) NOT NULL,
    peso        DOUBLE PRECISION DEFAULT 1.0,
    origen      VARCHAR(20) DEFAULT 'onboarding',
    PRIMARY KEY (cliente_id, tipo, valor)
);

CREATE TABLE IF NOT EXISTS tickets (
    id           VARCHAR(24) PRIMARY KEY,
    cliente_id   VARCHAR(20) REFERENCES clientes(id) ON DELETE CASCADE,
    tienda_id    VARCHAR(10),
    fecha        TIMESTAMP    NOT NULL,
    total        DOUBLE PRECISION NOT NULL,
    metodo_pago  VARCHAR(20),                   -- tarjeta | efectivo | online
    origen       VARCHAR(20),                   -- ticket_digital | foto | online | manual
    hash_dedupe  VARCHAR(64) UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_tickets_cliente_fecha ON tickets (cliente_id, fecha);

CREATE TABLE IF NOT EXISTS lineas_ticket (
    id               SERIAL PRIMARY KEY,
    ticket_id        VARCHAR(24) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    producto_id      VARCHAR(10) NOT NULL REFERENCES productos(id),
    cantidad         INTEGER      NOT NULL,
    precio_unitario  DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lineas_ticket ON lineas_ticket (ticket_id);
CREATE INDEX IF NOT EXISTS idx_lineas_producto ON lineas_ticket (producto_id);

CREATE TABLE IF NOT EXISTS feedback (
    id           SERIAL PRIMARY KEY,
    cliente_id   VARCHAR(20) REFERENCES clientes(id) ON DELETE CASCADE,
    producto_id  VARCHAR(10) REFERENCES productos(id),
    tipo         VARCHAR(20),                   -- me_gusta | no_me_gusta | descartar
    fecha        TIMESTAMP DEFAULT now(),
    UNIQUE (cliente_id, producto_id, tipo)
);
