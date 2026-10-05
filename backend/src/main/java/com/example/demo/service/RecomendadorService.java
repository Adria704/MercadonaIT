package com.example.demo.service;

import com.example.demo.model.PerfilCliente;
import com.example.demo.model.Ticket;
import com.example.demo.repository.PerfilRepository;
import com.example.demo.repository.TicketRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class RecomendadorService {

    @Autowired
    private TicketRepository ticketRepository;
    
    @Autowired
    private PerfilRepository perfilRepository;

    private final String PYTHON_AI_URL = "http://localhost:8000/api/recomendacion";
    private final RestTemplate restTemplate = new RestTemplate();

    public String generarCompraPersonalizada(String clienteId) {
        System.out.println("\n[ORQUESTADOR AI] Iniciando generación de compra para el cliente: " + clienteId);

        System.out.println("[BASE DE DATOS] Extrayendo perfil de preferencias y últimos tickets...");
        PerfilCliente perfil = perfilRepository.findById(clienteId).orElse(null);
        List<Ticket> ultimosTickets = ticketRepository.findByClienteId(clienteId);

        System.out.println("[PAYLOAD] Empaquetando contexto filtrado para inyectar en el LLM...");
        Map<String, Object> payload = new HashMap<>();
        payload.put("clienteId", clienteId);
        payload.put("preferencias", perfil != null ? perfil.getPreferenciasJson() : "{}");
        payload.put("historial", ultimosTickets);

        System.out.println("[HTTP POST] Enviando datos al microservicio de Python (FastAPI)...");
        try {
            String respuesta = restTemplate.postForObject(PYTHON_AI_URL, payload, String.class);
            System.out.println("[RESPUESTA] Recomendación recibida con éxito desde la IA.");
            return respuesta;
        } catch (Exception e) {
            System.out.println("[ERROR] El motor de IA en Python no responde. ¿Está FastAPI levantado?");
            return "{\"error\": \"El motor de IA en Python está apagado o fallando.\"}";
        }
    }
}