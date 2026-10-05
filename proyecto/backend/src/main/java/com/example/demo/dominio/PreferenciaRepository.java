package com.example.demo.dominio;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PreferenciaRepository extends JpaRepository<Preferencia, PreferenciaId> {
    List<Preferencia> findByClienteId(String clienteId);
}
