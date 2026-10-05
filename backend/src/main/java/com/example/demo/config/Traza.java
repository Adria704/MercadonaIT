package com.example.demo.config;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

/**
 * Trazas visuales en la consola del backend para la demo "solo backend".
 *
 *   +--------------------------------------------------------------------------+
 *   | POST   /api/clientes/C0001/chat                                 12:16:03 |
 *   +--------------------------------------------------------------------------+
 *     SPRING  --->  POSTGRES   Cliente C0001: 3 preferencias y 140 tickets
 *     SPRING  --->  IA         Llamando al servicio de IA (Python/FastAPI)...
 *     IA      --->  LLM        Herramientas usadas: preparar_cesta | Modelo: ollama
 *     SPRING  <---  IA         OK en 120 ms
 *     <== 200 OK               [###.................] 135 ms
 *
 * Colores ANSI (se desactivan con app.trazas.color: false si la consola muestra caracteres raros).
 * Sin tildes ni simbolos especiales a proposito: la consola de Windows a veces los muestra mal.
 */
public final class Traza {
    private static final DateTimeFormatter HORA = DateTimeFormatter.ofPattern("HH:mm:ss");
    private static final int ANCHO = 78;
    private static final String RESET = "\u001B[0m", NEGRITA = "\u001B[1m";
    private static final String VERDE = "\u001B[32m", AMARILLO = "\u001B[33m", AZUL = "\u001B[34m";
    private static final String MAGENTA = "\u001B[35m", CIAN = "\u001B[36m", ROJO = "\u001B[31m", GRIS = "\u001B[90m";

    private static volatile boolean color = true;

    private Traza() {
    }

    public static void activarColor(boolean activar) {
        color = activar;
    }

    private static String c(String codigo, String texto) {
        return color ? codigo + texto + RESET : texto;
    }

    private static String ajustar(String texto, int ancho) {
        if (texto.length() > ancho) return texto.substring(0, ancho - 3) + "...";
        return texto + " ".repeat(ancho - texto.length());
    }

    /** Caja de cabecera de cada peticion (la pinta TrazaInterceptor). */
    public static void inicio(String metodo, String ruta) {
        String linea = "+" + "-".repeat(ANCHO - 2) + "+";
        int anchoRuta = ANCHO - 4 - 7 - 8;
        System.out.println();
        System.out.println(c(GRIS, linea));
        System.out.println(c(GRIS, "| ") + c(NEGRITA + VERDE, ajustar(metodo, 7)) + c(NEGRITA, ajustar(ruta, anchoRuta))
                + c(GRIS, LocalTime.now().format(HORA) + " |"));
        System.out.println(c(GRIS, linea));
    }

    /** Un paso del recorrido. La etiqueta decide la flecha y el color. */
    public static void paso(String etiqueta, String mensaje) {
        String flecha, col;
        if (etiqueta.startsWith("HTTP")) {
            flecha = "SPRING  --->  IA";
            col = CIAN;
        } else {
            switch (etiqueta) {
                case "BASE DE DATOS" -> { flecha = "SPRING  --->  POSTGRES"; col = AZUL; }
                case "RESPUESTA IA" -> { flecha = "SPRING  <---  IA"; col = mensaje.startsWith("OK") ? CIAN : ROJO; }
                case "IA" -> {
                    boolean llm = mensaje.startsWith("Herramientas");
                    flecha = llm ? "IA      --->  LLM" : "IA      ===>  RESULTADO";
                    col = MAGENTA;
                }
                case "TICKET DIGITAL" -> { flecha = "#  TICKET DIGITAL"; col = VERDE; }
                case "DEDUPLICADO" -> { flecha = "=  DEDUPLICADO"; col = AMARILLO; }
                case "ERROR" -> { flecha = "!! ERROR"; col = NEGRITA + ROJO; }
                default -> { flecha = "*  " + etiqueta; col = AMARILLO; }  // ORQUESTADOR, PAYLOAD...
            }
        }
        System.out.println("  " + c(col, ajustar(flecha, 24)) + " " + mensaje);
    }

    /** Pie de cada peticion: codigo de respuesta y barra de tiempo (1 bloque = 50 ms). */
    public static void fin(int estado, long ms) {
        boolean ok = estado < 400;
        int bloques = (int) Math.min(20, Math.max(1, ms / 50));
        String barra = "[" + "#".repeat(bloques) + ".".repeat(20 - bloques) + "]";
        String texto = switch (estado) {
            case 200 -> "OK";
            case 201 -> "Creado";
            case 400 -> "Peticion incorrecta";
            case 404 -> "No encontrado";
            case 503 -> "IA no disponible";
            default -> "";
        };
        System.out.println("  " + c(NEGRITA + (ok ? VERDE : ROJO), ajustar((ok ? "<== " : "<!! ") + estado + " " + texto, 24))
                + " " + c(ok ? VERDE : ROJO, barra) + " " + ms + " ms");
    }

    /** Recuadro de arranque con las direcciones utiles. */
    public static void listo(int puerto, String iaUrl) {
        String linea = "=".repeat(ANCHO);
        System.out.println();
        System.out.println(c(VERDE, linea));
        System.out.println(c(NEGRITA + VERDE, "  DONA, no te abandona") + c(GRIS, "   -   backend Spring Boot listo"));
        System.out.println(c(VERDE, linea));
        System.out.println("  App web ........ " + c(NEGRITA, "http://localhost:" + puerto));
        System.out.println("  API ............ " + c(NEGRITA, "http://localhost:" + puerto + "/api/status"));
        System.out.println("  Servicio de IA . " + c(NEGRITA, iaUrl));
        System.out.println("  Demo consola ... " + c(AMARILLO, ".\\demo-backend.ps1") + c(GRIS, "  (en otra ventana, carpeta backend)"));
        System.out.println(c(VERDE, linea));
    }
}
