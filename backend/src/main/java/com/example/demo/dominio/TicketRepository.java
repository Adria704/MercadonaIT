package com.example.demo.dominio;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TicketRepository extends JpaRepository<Ticket, String> {
    List<Ticket> findTop20ByClienteIdOrderByFechaDesc(String clienteId);

    boolean existsByHashDedupe(String hashDedupe);

    long countByClienteId(String clienteId);
}
