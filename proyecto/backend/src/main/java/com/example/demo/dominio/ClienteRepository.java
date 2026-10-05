package com.example.demo.dominio;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ClienteRepository extends JpaRepository<Cliente, String> {
    Optional<Cliente> findByTelefono(String telefono);

    Optional<Cliente> findByTarjetaToken(String tarjetaToken);

    long countByIdStartingWith(String prefijo);
}
