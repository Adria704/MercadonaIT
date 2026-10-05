package com.example.demo.controller;

import com.example.demo.model.Ticket;
import com.example.demo.repository.TicketRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import com.example.demo.service.RecomendadorService;

import java.util.List;

@RestController
@RequestMapping("/api/tickets")
public class TicketController {

    @Autowired
    private TicketRepository ticketRepository;

    @Autowired
    private RecomendadorService recomendadorService;

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

    @PostMapping("/{clienteId}/recomendacion")
    public ResponseEntity<String> solicitarRecomendacion(@PathVariable String clienteId) {
        System.out.println("\n--- NUEVA PETICIÓN HTTP RECIBIDA: /api/tickets/" + clienteId + "/recomendacion ---");
        String recomendacion = recomendadorService.generarCompraPersonalizada(clienteId);
        return ResponseEntity.ok(recomendacion);
    }
}