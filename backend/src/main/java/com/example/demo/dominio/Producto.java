package com.example.demo.dominio;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Tabla productos (catálogo). Solo lectura desde el backend. */
@Entity
@Table(name = "productos")
public class Producto {
    @Id
    private String id;
    private String clave;
    private String nombre;
    private String marca;
    private String seccion;
    private String categoria;
    private Double precio;
    @Column(name = "formato_g")
    private Integer formatoG;
    private String alergenos;
    private String trazas;
    private String etiquetas;
    private String envase;
    private Boolean sensible;

    protected Producto() {
    }

    public String getId() { return id; }
    public String getClave() { return clave; }
    public String getNombre() { return nombre; }
    public String getMarca() { return marca; }
    public String getSeccion() { return seccion; }
    public String getCategoria() { return categoria; }
    public Double getPrecio() { return precio; }
    public Integer getFormatoG() { return formatoG; }
    public String getAlergenos() { return alergenos; }
    public String getTrazas() { return trazas; }
    public String getEtiquetas() { return etiquetas; }
    public String getEnvase() { return envase; }
    public Boolean getSensible() { return sensible; }
}
