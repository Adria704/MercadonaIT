package com.example.demo.dominio;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

/** Tabla tickets (cabecera del ticket digital). */
@Entity
@Table(name = "tickets")
public class Ticket {
    @Id
    private String id;
    @Column(name = "cliente_id")
    private String clienteId;
    @Column(name = "tienda_id")
    private String tiendaId;
    private LocalDateTime fecha;
    private Double total;
    @Column(name = "metodo_pago")
    private String metodoPago;
    private String origen;
    @Column(name = "hash_dedupe")
    private String hashDedupe;

    protected Ticket() {
    }

    public Ticket(String id, String clienteId, String tiendaId, LocalDateTime fecha, Double total,
                  String metodoPago, String origen, String hashDedupe) {
        this.id = id;
        this.clienteId = clienteId;
        this.tiendaId = tiendaId;
        this.fecha = fecha;
        this.total = total;
        this.metodoPago = metodoPago;
        this.origen = origen;
        this.hashDedupe = hashDedupe;
    }

    public String getId() { return id; }
    public String getClienteId() { return clienteId; }
    public String getTiendaId() { return tiendaId; }
    public LocalDateTime getFecha() { return fecha; }
    public Double getTotal() { return total; }
    public String getMetodoPago() { return metodoPago; }
    public String getOrigen() { return origen; }
    public String getHashDedupe() { return hashDedupe; }
}
