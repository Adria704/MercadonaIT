package com.example.demo.dominio;

import java.io.Serializable;
import java.util.Objects;

/** Clave compuesta de preferencias: (cliente_id, tipo, valor). */
public class PreferenciaId implements Serializable {
    private String clienteId;
    private String tipo;
    private String valor;

    public PreferenciaId() {
    }

    public PreferenciaId(String clienteId, String tipo, String valor) {
        this.clienteId = clienteId;
        this.tipo = tipo;
        this.valor = valor;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof PreferenciaId p)) return false;
        return Objects.equals(clienteId, p.clienteId) && Objects.equals(tipo, p.tipo) && Objects.equals(valor, p.valor);
    }

    @Override
    public int hashCode() {
        return Objects.hash(clienteId, tipo, valor);
    }
}
