package com.example.demo.dominio;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

/** Tabla preferencias: intereses del onboarding (tipo "interes"), restricciones y alergias. */
@Entity
@Table(name = "preferencias")
@IdClass(PreferenciaId.class)
public class Preferencia {
    @Id
    @Column(name = "cliente_id")
    private String clienteId;
    @Id
    private String tipo;
    @Id
    private String valor;
    private Double peso;
    private String origen;

    protected Preferencia() {
    }

    public Preferencia(String clienteId, String tipo, String valor) {
        this.clienteId = clienteId;
        this.tipo = tipo;
        this.valor = valor;
        this.peso = 1.0;
        this.origen = "onboarding";
    }

    public String getClienteId() { return clienteId; }
    public String getTipo() { return tipo; }
    public String getValor() { return valor; }
    public Double getPeso() { return peso; }
    public String getOrigen() { return origen; }
}
