package com.example.demo.ia;

import com.example.demo.config.Traza;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.function.Function;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.util.UriBuilder;

/**
 * Cliente HTTP del servicio de IA (FastAPI, Python).
 * Reenvía el JSON tal cual (sin mapearlo a clases Java): si el servicio de IA añade campos,
 * el frontend los recibe sin tocar el backend.
 */
@Component
public class IaClient {

    private final RestClient http;
    private final String baseUrl;

    public IaClient(@Value("${ia.url}") String baseUrl, @Value("${ia.timeout-segundos:180}") long timeoutSegundos) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(timeoutSegundos));
        this.baseUrl = baseUrl;
        this.http = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    public ResponseEntity<String> get(Function<UriBuilder, java.net.URI> uri) {
        return enviar(HttpMethod.GET, uri, null);
    }

    public ResponseEntity<String> post(Function<UriBuilder, java.net.URI> uri, String cuerpoJson) {
        return enviar(HttpMethod.POST, uri, cuerpoJson == null || cuerpoJson.isBlank() ? "{}" : cuerpoJson);
    }

    private static final MediaType JSON_UTF8 = new MediaType("application", "json", StandardCharsets.UTF_8);

    private ResponseEntity<String> enviar(HttpMethod metodo, Function<UriBuilder, java.net.URI> uri, String cuerpoJson) {
        long t0 = System.currentTimeMillis();
        try {
            RestClient.RequestBodySpec peticion = http.method(metodo).uri(uri);
            if (cuerpoJson != null) {
                peticion.contentType(MediaType.APPLICATION_JSON).body(cuerpoJson);
            }
            Traza.paso("HTTP " + metodo.name(), "Llamando al servicio de IA (Python/FastAPI) en " + baseUrl + "...");
            String respuesta = peticion.retrieve().body(String.class);
            Traza.paso("RESPUESTA IA", "OK en " + (System.currentTimeMillis() - t0) + " ms ("
                    + (respuesta == null ? 0 : respuesta.length()) + " caracteres)");
            return ResponseEntity.ok().contentType(JSON_UTF8).body(respuesta);
        } catch (RestClientResponseException e) {
            // Error devuelto por el servicio de IA (404 cliente no encontrado, 503 sin LLM...): se reenvía igual
            Traza.paso("RESPUESTA IA", "Error " + e.getStatusCode().value() + " devuelto por el servicio de IA");
            return ResponseEntity.status(e.getStatusCode()).contentType(JSON_UTF8)
                    .body(e.getResponseBodyAsString());
        } catch (ResourceAccessException e) {
            Traza.paso("ERROR", "El servicio de IA no responde en " + baseUrl + ". Esta arrancado?");
            return ResponseEntity.status(503).contentType(JSON_UTF8)
                    .body("{\"error\": \"El servicio de IA no responde en " + baseUrl
                            + ". Arráncalo con: python -m uvicorn app.main:app --port 8001\"}");
        }
    }
}
