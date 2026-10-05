package com.example.demo.controller;

import com.example.demo.model.Ticket;
import com.example.demo.repository.TicketRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/tickets")
public class TicketController {

    @Autowired
    private TicketRepository ticketRepository;

    @PostMapping
    public ResponseEntity<Ticket> guardarTicket(@RequestBody Ticket ticket) {
        Ticket ticketGuardado = ticketRepository.save(ticket);
        return ResponseEntity.ok(ticketGuardado);
    }

    @GetMapping("/{clienteId}")
    public ResponseEntity<List<Ticket>> obtenerTicketsPorCliente(@PathVariable String clienteId) {
        List<Ticket> historial = ticketRepository.findByClienteId(clienteId);
        return ResponseEntity.ok(historial);
    }
}