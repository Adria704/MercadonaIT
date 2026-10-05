package com.example.demo.tickets;

import com.example.demo.config.Json;
import com.example.demo.dominio.Cliente;
import com.example.demo.dominio.ClienteRepository;
import com.example.demo.dominio.LineaTicket;
import com.example.demo.dominio.LineaTicketRepository;
import com.example.demo.dominio.Producto;
import com.example.demo.dominio.ProductoRepository;
import com.example.demo.dominio.Ticket;
import com.example.demo.dominio.TicketRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Ingesta del ticket digital: cada compra asociada a la tarjeta o al teléfono se guarda línea a línea.
 * También acepta tickets de pagos en efectivo (foto del ticket o entrada manual) con origen distinto.
 * Deduplicado: mismo cliente + tienda + minuto + importe = mismo ticket (mismo criterio que el servicio de IA).
 */
@Service
public class TicketService {

    private static final DateTimeFormatter MINUTO = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");
    private static final DateTimeFormatter ID = DateTimeFormatter.ofPattern("yyMMddHHmmssSSS");

    private final ClienteRepository clientes;
    private final ProductoRepository productos;
    private final TicketRepository tickets;
    private final LineaTicketRepository lineas;

    public TicketService(ClienteRepository clientes, ProductoRepository productos, TicketRepository tickets,
                         LineaTicketRepository lineas) {
        this.clientes = clientes;
        this.productos = productos;
        this.tickets = tickets;
        this.lineas = lineas;
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> registrar(Map<String, Object> entrada) {
        // Compatibilidad con el primer formato del equipo: {"clienteId": "...", "contenidoJson": {...ticket...}}
        Map<String, Object> cuerpo = new LinkedHashMap<>(entrada);
        Object contenido = entrada.containsKey("contenido_json") ? entrada.get("contenido_json") : entrada.get("contenidoJson");
        if (contenido instanceof Map<?, ?> c) {
            ((Map<String, Object>) c).forEach(cuerpo::putIfAbsent);
        }
        String clienteId = Json.texto(cuerpo, "cliente_id", "clienteId");
        String telefono = Json.texto(cuerpo, "telefono", "telefono");
        String tarjeta = Json.texto(cuerpo, "tarjeta_token", "tarjetaToken");
        Cliente cliente = (clienteId != null ? clientes.findById(clienteId)
                : telefono != null ? clientes.findByTelefono(telefono) : clientes.findByTarjetaToken(String.valueOf(tarjeta)))
                .orElseThrow(() -> new IllegalArgumentException("Ticket sin cliente asociado (cliente, teléfono o tarjeta desconocidos)"));

        String tienda = valor(Json.texto(cuerpo, "tienda_id", "tiendaId"), "T01");
        String fechaTxt = Json.texto(cuerpo, "fecha", "fecha");
        LocalDateTime fecha = fechaTxt == null ? LocalDateTime.now().withNano(0) : LocalDateTime.parse(fechaTxt);
        String metodoPago = valor(Json.texto(cuerpo, "metodo_pago", "metodoPago"), "tarjeta");
        String origen = valor(Json.texto(cuerpo, "origen", "origen"), "ticket_digital");

        List<Object> lineasEntrada = Json.lista(cuerpo, "lineas");
        if (lineasEntrada.isEmpty()) {
            throw new IllegalArgumentException("El ticket no tiene líneas");
        }
        List<LineaTicket> nuevas = new ArrayList<>();
        double total = 0;
        String idTicket = "S" + LocalDateTime.now().format(ID) + ThreadLocalRandom.current().nextInt(100, 1000);
        for (Object o : lineasEntrada) {
            Map<String, Object> l = (Map<String, Object>) o;
            String productoId = Json.texto(l, "producto_id", "productoId");
            Producto p = productos.findById(String.valueOf(productoId))
                    .orElseThrow(() -> new IllegalArgumentException("Producto desconocido: " + productoId));
            int cantidad = valor(Json.entero(l, "cantidad", "cantidad"), 1);
            double precio = valor(Json.decimal(l, "precio_unitario", "precioUnitario"), p.getPrecio());
            total += cantidad * precio;
            nuevas.add(new LineaTicket(idTicket, p.getId(), cantidad, precio));
        }
        total = Math.round(total * 100.0) / 100.0;

        String hash = sha256(cliente.getId() + "|" + tienda + "|" + fecha.format(MINUTO) + "|" + String.format(Locale.ROOT, "%.2f", total));
        Map<String, Object> r = new LinkedHashMap<>();
        if (tickets.existsByHashDedupe(hash)) {
            r.put("duplicado", true);
            r.put("mensaje", "Este ticket ya estaba registrado");
            return r;
        }
        tickets.save(new Ticket(idTicket, cliente.getId(), tienda, fecha, total, metodoPago, origen, hash));
        lineas.saveAll(nuevas);

        r.put("duplicado", false);
        r.put("ticket_id", idTicket);
        r.put("cliente_id", cliente.getId());
        r.put("total", total);
        r.put("lineas", nuevas.size());
        return r;
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> ultimos(String clienteId, int limite) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Ticket t : tickets.findTop20ByClienteIdOrderByFechaDesc(clienteId).stream().limit(limite).toList()) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", t.getId());
            m.put("fecha", t.getFecha().toString());
            m.put("tienda_id", t.getTiendaId());
            m.put("total", t.getTotal());
            m.put("metodo_pago", t.getMetodoPago());
            m.put("origen", t.getOrigen());
            List<Map<String, Object>> ls = new ArrayList<>();
            for (LineaTicket l : lineas.findByTicketId(t.getId())) {
                Producto p = productos.findById(l.getProductoId()).orElse(null);
                if (p != null && Boolean.TRUE.equals(p.getSensible())) {
                    continue; // privacidad: los productos sensibles no se muestran en listados
                }
                Map<String, Object> lm = new LinkedHashMap<>();
                lm.put("producto_id", l.getProductoId());
                lm.put("nombre", p == null ? l.getProductoId() : p.getNombre());
                lm.put("cantidad", l.getCantidad());
                lm.put("precio_unitario", l.getPrecioUnitario());
                ls.add(lm);
            }
            m.put("lineas", ls);
            out.add(m);
        }
        return out;
    }

    private static <T> T valor(T v, T porDefecto) {
        return v == null ? porDefecto : v;
    }

    private static String sha256(String texto) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(texto.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
