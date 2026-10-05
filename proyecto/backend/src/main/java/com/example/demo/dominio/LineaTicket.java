package com.example.demo.dominio;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Tabla lineas_ticket (cada producto de un ticket). */
@Entity
@Table(name = "lineas_ticket")
public class LineaTicket {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;
    @Column(name = "ticket_id")
    private String ticketId;
    @Column(name = "producto_id")
    private String productoId;
    private Integer cantidad;
    @Column(name = "precio_unitario")
    private Double precioUnitario;

    protected LineaTicket() {
    }

    public LineaTicket(String ticketId, String productoId, Integer cantidad, Double precioUnitario) {
        this.ticketId = ticketId;
        this.productoId = productoId;
        this.cantidad = cantidad;
        this.precioUnitario = precioUnitario;
    }

    public Integer getId() { return id; }
    public String getTicketId() { return ticketId; }
    public String getProductoId() { return productoId; }
    public Integer getCantidad() { return cantidad; }
    public Double getPrecioUnitario() { return precioUnitario; }
}
