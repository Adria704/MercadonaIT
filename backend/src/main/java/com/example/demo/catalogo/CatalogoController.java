package com.example.demo.catalogo;

import com.example.demo.config.Traza;
import com.example.demo.dominio.Producto;
import com.example.demo.dominio.ProductoRepository;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Catálogo de productos (lectura directa de PostgreSQL con JPA). */
@RestController
@RequestMapping("/api/productos")
public class CatalogoController {

    private final ProductoRepository productos;

    public CatalogoController(ProductoRepository productos) {
        this.productos = productos;
    }

    @GetMapping
    public List<Map<String, Object>> buscar(@RequestParam(defaultValue = "") String q) {
        List<Map<String, Object>> r = productos.findTop20ByNombreContainingIgnoreCaseAndSensibleFalseOrderByNombreAsc(q.trim())
                .stream().map(CatalogoController::aMapa).toList();
        Traza.paso("BASE DE DATOS", r.size() + " productos encontrados en el catalogo");
        return r;
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> ver(@PathVariable String id) {
        return productos.findById(id).map(p -> ResponseEntity.ok(aMapa(p)))
                .orElse(ResponseEntity.notFound().build());
    }

    public static Map<String, Object> aMapa(Producto p) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", p.getId());
        m.put("nombre", p.getNombre());
        m.put("marca", p.getMarca());
        m.put("seccion", p.getSeccion());
        m.put("categoria", p.getCategoria());
        m.put("precio", p.getPrecio());
        m.put("formato_g", p.getFormatoG());
        m.put("alergenos", separar(p.getAlergenos()));
        m.put("trazas", separar(p.getTrazas()));
        m.put("etiquetas", separar(p.getEtiquetas()));
        return m;
    }

    private static List<String> separar(String csv) {
        return csv == null || csv.isBlank() ? List.of() : Arrays.stream(csv.split(",")).filter(s -> !s.isBlank()).toList();
    }
}
