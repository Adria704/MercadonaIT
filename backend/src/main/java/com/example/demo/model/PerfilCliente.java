package com.example.demo.model;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "perfiles")
public class PerfilCliente {

    @Id
    private String clienteId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", nullable = false)
    private String preferenciasJson;

    public PerfilCliente() {}

    public String getClienteId() { return clienteId; }
    public void setClienteId(String clienteId) { this.clienteId = clienteId; }
    public String getPreferenciasJson() { return preferenciasJson; }
    public void setPreferenciasJson(String preferenciasJson) { this.preferenciasJson = preferenciasJson; }
}