package com.example.demo.clientes;

import com.example.demo.config.Json;
import com.example.demo.dominio.Cliente;
import com.example.demo.dominio.Preferencia;
import com.example.demo.dominio.PreferenciaRepository;
import com.example.demo.dominio.TicketRepository;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Cuentas de cliente: alta (onboarding) e identificación por teléfono o tarjeta (como el ticket digital). */
@RestController
@RequestMapping("/api/clientes")
public class ClienteController {

    private final ClienteService servicio;
    private final PreferenciaRepository preferencias;
    private final TicketRepository tickets;

    public ClienteController(ClienteService servicio, PreferenciaRepository preferencias, TicketRepository tickets) {
        this.servicio = servicio;
        this.preferencias = preferencias;
        this.tickets = tickets;
    }

    /** Cuerpo: {"telefono": "600111222"} o {"tarjeta_token": "..."} */
    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(@RequestBody Map<String, Object> cuerpo) {
        return servicio.identificar(Json.texto(cuerpo, "telefono", "telefono"), Json.texto(cuerpo, "tarjeta_token", "tarjetaToken"))
                .map(c -> ResponseEntity.ok(aMapa(c)))
                .orElse(ResponseEntity.status(404).body(Map.of("error", "No hay ninguna cuenta con ese teléfono o tarjeta")));
    }

    /**
     * Alta. Cuerpo: {"nombre": "Pepa", "telefono": "611222333", "intereses": ["desayunos", "fitness"],
     * "restricciones": ["sin_gluten"], "alergias": ["frutos_secos"]}.
     * Los ids válidos de intereses están en GET /api/onboarding/intereses.
     */
    @PostMapping
    public ResponseEntity<Map<String, Object>> crear(@RequestBody Map<String, Object> cuerpo) {
        try {
            Cliente c = servicio.crear(Json.texto(cuerpo, "nombre", "nombre"), Json.texto(cuerpo, "telefono", "telefono"),
                    textos(Json.lista(cuerpo, "intereses")), textos(Json.lista(cuerpo, "restricciones")),
                    textos(Json.lista(cuerpo, "alergias")));
            return ResponseEntity.status(201).body(aMapa(c));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    /** Resumen básico desde el backend (para el perfil completo con gustos aprendidos: /api/clientes/{id}/perfil). */
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> ver(@PathVariable String id) {
        return servicio.identificarPorId(id)
                .map(c -> {
                    Map<String, Object> m = aMapa(c);
                    m.put("preferencias", preferencias.findByClienteId(id).stream().map(ClienteController::pref).toList());
                    m.put("tickets_guardados", tickets.countByClienteId(id));
                    return ResponseEntity.ok(m);
                })
                .orElse(ResponseEntity.notFound().build());
    }

    private static Map<String, Object> pref(Preferencia p) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("tipo", p.getTipo());
        m.put("valor", p.getValor());
        m.put("peso", p.getPeso());
        m.put("origen", p.getOrigen());
        return m;
    }

    static Map<String, Object> aMapa(Cliente c) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", c.getId());
        m.put("nombre", c.getNombre());
        m.put("telefono", c.getTelefono());
        m.put("creado_en", c.getCreadoEn() == null ? null : c.getCreadoEn().toString());
        return m;
    }

    private static List<String> textos(List<Object> l) {
        return l.stream().map(Object::toString).toList();
    }
}
