package com.example.demo.ia;

import java.util.Optional;
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

    private final IaClient ia;

    public IaController(IaClient ia) {
        this.ia = ia;
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
        return ia.get(u -> u.path("/clientes/{id}/recomendaciones").queryParam("n", n).build(id));
    }

    /** Cuerpo: {"mensaje": "¿Cuánto llevo gastado este mes?"} */
    @PostMapping("/clientes/{id}/chat")
    public ResponseEntity<String> chat(@PathVariable String id, @RequestBody String cuerpo) {
        return ia.post(u -> u.path("/clientes/{id}/chat").build(id), cuerpo);
    }

    /** Cesta de Dona directa (sin pasar por el chat), p. ej. para "Otra propuesta".
     *  Cuerpo: {"presupuesto": 30, "personas": 3, "restricciones": ["sin_gluten"], "alergias": [], "variante": 1} */
    @PostMapping("/clientes/{id}/cesta")
    public ResponseEntity<String> cesta(@PathVariable String id, @RequestBody String cuerpo) {
        return ia.post(u -> u.path("/clientes/{id}/cesta").build(id), cuerpo);
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

    /** periodo: "2026" (año), "2026-09" (mes) o vacío (último año). llm=false: plantilla instantánea. */
    @GetMapping("/clientes/{id}/wrapped")
    public ResponseEntity<String> wrapped(@PathVariable String id,
                                          @RequestParam(required = false) String periodo,
                                          @RequestParam(defaultValue = "true") boolean llm) {
        return ia.get(u -> u.path("/clientes/{id}/wrapped")
                .queryParamIfPresent("periodo", Optional.ofNullable(periodo))
                .queryParam("llm", llm)
                .build(id));
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
