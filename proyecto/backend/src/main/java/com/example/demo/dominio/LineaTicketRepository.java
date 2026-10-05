package com.example.demo.dominio;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LineaTicketRepository extends JpaRepository<LineaTicket, Integer> {
    List<LineaTicket> findByTicketId(String ticketId);
}
