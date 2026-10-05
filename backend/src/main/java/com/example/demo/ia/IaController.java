package com.example.demo.ia;

import com.example.demo.config.Traza;
import com.example.demo.dominio.PreferenciaRepository;
import com.example.demo.dominio.TicketRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Endpoints de IA expuestos al frontend. El backend es la única puerta de entrada:
 * el frontend nunca llama directamente al servicio de Python.
 */
@RestController
@RequestMapping("/api")
public class IaController {

    private static final Pattern HERRAMIENTA = Pattern.compile("\"tipo\":\"herramienta\",\"nombre\":\"([a-z_]+)\"");
    private static final Pattern PROVEEDORES = Pattern.compile("\"proveedores\":\\[([^\\]]*)\\]");
    private static final Pattern ADAPTACION = Pattern.compile("\"mensaje\":\"(Basado[^\"]*)\"");
    private static final Pattern TOTAL_CESTA = Pattern.compile("\"total\":([0-9.]+),\"presupuesto\":([0-9.]+)");

    private final IaClient ia;
    private final PreferenciaRepository preferencias;
    private final TicketRepository tickets;

    public IaController(IaClient ia, PreferenciaRepository preferencias, TicketRepository tickets) {
        this.ia = ia;
        this.preferencias = preferencias;
        this.tickets = tickets;
    }

    /** Contexto que el servicio de IA usara (para que en la consola se vea con que datos trabaja). */
    private void contexto(String id) {
        Traza.paso("BASE DE DATOS", "Cliente " + id + ": " + preferencias.findByClienteId(id).size()
                + " preferencias y " + tickets.countByClienteId(id) + " tickets guardados en PostgreSQL");
    }

    private static List<String> buscar(Pattern p, String texto) {
        List<String> out = new ArrayList<>();
        if (texto == null) return out;
        Matcher m = p.matcher(texto);
        while (m.find()) out.add(m.group(1));
        return out;
    }

    private static void resumenRecomendaciones(ResponseEntity<String> r) {
        List<String> a = buscar(ADAPTACION, r.getBody());
        if (!a.isEmpty()) Traza.paso("IA", a.get(0));
    }

    /**
     * Ruta que definio el equipo para la demo del backend: genera las recomendaciones personalizadas del cliente
     * (mismo resultado que GET /api/clientes/{id}/recomendaciones), mostrando cada paso en la consola.
     */
    @PostMapping("/tickets/{id}/recomendacion")
    public ResponseEntity<String> recomendacionDemo(@PathVariable String id) {
        Traza.paso("ORQUESTADOR", "Iniciando la recomendacion personalizada para el cliente " + id);
        contexto(id);
        Traza.paso("PAYLOAD", "El servicio de IA lee el historial y los gustos de la misma base de datos");
        ResponseEntity<String> r = ia.get(u -> u.path("/clientes/{id}/recomendaciones").build(id));
        resumenRecomendaciones(r);
        return r;
    }

    /** Estado del servicio de IA: qué LLM está disponible (Qwen local, API gratuita o modo sin IA). */
    @GetMapping("/ia/estado")
    public ResponseEntity<String> estado() {
        return ia.get(u -> u.path("/config").build());
    }

    /** Tarjetas tipo Pinterest para el alta, restricciones y alérgenos. */
    @GetMapping("/onboarding/intereses")
    public ResponseEntity<String> intereses() {
        return ia.get(u -> u.path("/onboarding/intereses").build());
    }

    @GetMapping("/clientes/{id}/recomendaciones")
    public ResponseEntity<String> recomendaciones(@PathVariable String id, @RequestParam(defaultValue = "6") int n) {
        contexto(id);
        ResponseEntity<String> r = ia.get(u -> u.path("/clientes/{id}/recomendaciones").queryParam("n", n).build(id));
        resumenRecomendaciones(r);
        return r;
    }

    /** Cuerpo: {"mensaje": "¿Cuánto llevo gastado este mes?"} */
    @PostMapping("/clientes/{id}/chat")
    public ResponseEntity<String> chat(@PathVariable String id, @RequestBody String cuerpo) {
        contexto(id);
        Traza.paso("ORQUESTADOR", "Mensaje para Dona: el agente decide que herramientas usar");
        ResponseEntity<String> r = ia.post(u -> u.path("/clientes/{id}/chat").build(id), cuerpo);
        List<String> herramientas = buscar(HERRAMIENTA, r.getBody());
        List<String> proveedor = buscar(PROVEEDORES, r.getBody());
        Traza.paso("IA", "Herramientas usadas: " + (herramientas.isEmpty() ? "ninguna" : String.join(", ", herramientas))
                + (proveedor.isEmpty() ? "" : " | Modelo: " + proveedor.get(0).replace("\"", "")));
        return r;
    }

    /** Cesta de Dona directa (sin pasar por el chat), p. ej. para "Otra propuesta".
     *  Cuerpo: {"presupuesto": 30, "personas": 3, "restricciones": ["sin_gluten"], "alergias": [], "variante": 1} */
    @PostMapping("/clientes/{id}/cesta")
    public ResponseEntity<String> cesta(@PathVariable String id, @RequestBody String cuerpo) {
        contexto(id);
        ResponseEntity<String> r = ia.post(u -> u.path("/clientes/{id}/cesta").build(id), cuerpo);
        Matcher m = r.getBody() == null ? null : TOTAL_CESTA.matcher(r.getBody());
        if (m != null && m.find()) Traza.paso("IA", "Cesta de " + m.group(1) + " EUR para un presupuesto de " + m.group(2) + " EUR");
        return r;
    }

    @PostMapping("/clientes/{id}/chat/reset")
    public ResponseEntity<String> chatReset(@PathVariable String id) {
        return ia.post(u -> u.path("/clientes/{id}/chat/reset").build(id), "{}");
    }

    /** Cuerpo: {"me_gusta": ["salmón"], "no_me_gusta": ["pescado"]} */
    @PostMapping("/clientes/{id}/gustos")
    public ResponseEntity<String> gustos(@PathVariable String id, @RequestBody String cuerpo) {
        return ia.post(u -> u.path("/clientes/{id}/gustos").build(id), cuerpo);
    }

    @GetMapping("/clientes/{id}/reciclaje")
    public ResponseEntity<String> reciclaje(@PathVariable String id,
                                            @RequestParam(name = "ticket_id", required = false) String ticketId) {
        return ia.get(u -> u.path("/clientes/{id}/reciclaje")
                .queryParamIfPresent("ticket_id", Optional.ofNullable(ticketId))
                .build(id));
    }

    /** Pantalla "Esto es lo que sé de ti": preferencias, gustos aprendidos y nº de tickets guardados. */
    @GetMapping("/clientes/{id}/perfil")
    public ResponseEntity<String> perfil(@PathVariable String id) {
        return ia.get(u -> u.path("/clientes/{id}/perfil").build(id));
    }

    @GetMapping("/productos/{id}/reciclaje")
    public ResponseEntity<String> reciclajeProducto(@PathVariable String id) {
        return ia.get(u -> u.path("/productos/{id}/reciclaje").build(id));
    }
}
