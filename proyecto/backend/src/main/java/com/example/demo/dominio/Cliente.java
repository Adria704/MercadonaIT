package com.example.demo.dominio;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;

/** Tabla clientes. El cliente se identifica por teléfono o por el token cifrado de su tarjeta. */
@Entity
@Table(name = "clientes")
public class Cliente {
    @Id
    private String id;
    private String nombre;
    private String telefono;
    @Column(name = "tarjeta_token")
    private String tarjetaToken;
    @Column(name = "creado_en")
    private LocalDateTime creadoEn;

    protected Cliente() {
    }

    public Cliente(String id, String nombre, String telefono, String tarjetaToken, LocalDateTime creadoEn) {
        this.id = id;
        this.nombre = nombre;
        this.telefono = telefono;
        this.tarjetaToken = tarjetaToken;
        this.creadoEn = creadoEn;
    }

    public String getId() { return id; }
    public String getNombre() { return nombre; }
    public String getTelefono() { return telefono; }
    public String getTarjetaToken() { return tarjetaToken; }
    public LocalDateTime getCreadoEn() { return creadoEn; }
}
