package com.example.demo.clientes;

import com.example.demo.dominio.Cliente;
import com.example.demo.dominio.ClienteRepository;
import com.example.demo.dominio.Preferencia;
import com.example.demo.dominio.PreferenciaRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Alta de clientes con sus gustos iniciales (onboarding tipo Pinterest) y restricciones. */
@Service
public class ClienteService {

    private final ClienteRepository clientes;
    private final PreferenciaRepository preferencias;

    public ClienteService(ClienteRepository clientes, PreferenciaRepository preferencias) {
        this.clientes = clientes;
        this.preferencias = preferencias;
    }

    public Optional<Cliente> identificar(String telefono, String tarjetaToken) {
        if (telefono != null && !telefono.isBlank()) {
            return clientes.findByTelefono(telefono.trim());
        }
        if (tarjetaToken != null && !tarjetaToken.isBlank()) {
            return clientes.findByTarjetaToken(tarjetaToken.trim());
        }
        return Optional.empty();
    }

    public Optional<Cliente> identificarPorId(String id) {
        return clientes.findById(id);
    }

    @Transactional
    public Cliente crear(String nombre, String telefono, List<String> intereses, List<String> restricciones,
                         List<String> alergias) {
        if (nombre == null || nombre.isBlank() || telefono == null || telefono.isBlank()) {
            throw new IllegalArgumentException("Nombre y teléfono son obligatorios");
        }
        if (clientes.findByTelefono(telefono.trim()).isPresent()) {
            throw new IllegalArgumentException("Ya existe una cuenta con ese teléfono");
        }
        // Mismo formato de id que el servicio de IA: C0001, C0002...
        long n = clientes.countByIdStartingWith("C");
        String id;
        do {
            n++;
            id = String.format("C%04d", n);
        } while (clientes.existsById(id));
        // En producción el token lo genera la pasarela de pago; aquí se simula. Nunca se guarda el número de tarjeta.
        Cliente c = clientes.save(new Cliente(id, nombre.trim(), telefono.trim(), token("tarjeta-" + id), LocalDateTime.now()));

        final String clienteId = id;
        List<Preferencia> prefs = new ArrayList<>();
        intereses.forEach(v -> prefs.add(new Preferencia(clienteId, "interes", v)));
        restricciones.forEach(v -> prefs.add(new Preferencia(clienteId, "restriccion", v)));
        alergias.forEach(v -> prefs.add(new Preferencia(clienteId, "alergia", v)));
        preferencias.saveAll(prefs);
        return c;
    }

    static String token(String texto) {
        try {
            byte[] h = MessageDigest.getInstance("SHA-256").digest(texto.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(h).substring(0, 32);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
