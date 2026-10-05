package com.example.demo.dominio;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductoRepository extends JpaRepository<Producto, String> {
    List<Producto> findTop20ByNombreContainingIgnoreCaseAndSensibleFalseOrderByNombreAsc(String texto);
}
