package com.example.demo.tickets;

import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class TicketController {

    private final TicketService servicio;

    public TicketController(TicketService servicio) {
        this.servicio = servicio;
    }

    /**
     * Registra un ticket digital. Cuerpo:
     * {"cliente_id": "C0001" (o "telefono" / "tarjeta_token"), "tienda_id": "T02", "metodo_pago": "tarjeta", "origen": "ticket_digital",
     *  "fecha": "2026-10-05T19:30:00", "lineas": [{"producto_id": "P0031", "cantidad": 2}]}
     * Después, las recomendaciones y el Wrapped ya lo tienen en cuenta (el servicio de IA lee la misma BD).
     * Envases de este ticket: GET /api/clientes/{id}/reciclaje?ticket_id=...
     */
    @PostMapping("/tickets")
    public ResponseEntity<Map<String, Object>> registrar(@RequestBody Map<String, Object> cuerpo) {
        try {
            Map<String, Object> r = servicio.registrar(cuerpo);
            return ResponseEntity.status(Boolean.TRUE.equals(r.get("duplicado")) ? 200 : 201).body(r);
        } catch (IllegalArgumentException | DateTimeParseException | ClassCastException e) {
            return ResponseEntity.badRequest().body(Map.of("error", String.valueOf(e.getMessage())));
        }
    }

    /** Últimos tickets del cliente con sus productos. */
    @GetMapping("/clientes/{id}/tickets")
    public List<Map<String, Object>> ultimos(@PathVariable String id, @RequestParam(defaultValue = "5") int limite) {
        return servicio.ultimos(id, Math.min(Math.max(limite, 1), 20));
    }

    /** Misma consulta con la ruta que definió el equipo al principio (GET /api/tickets/{clienteId}). */
    @GetMapping("/tickets/{clienteId}")
    public List<Map<String, Object>> historial(@PathVariable String clienteId) {
        return servicio.ultimos(clienteId, 20);
    }
}
