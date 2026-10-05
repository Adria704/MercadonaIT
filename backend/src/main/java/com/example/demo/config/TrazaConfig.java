package com.example.demo.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** Activa las trazas visuales de la consola (ver Traza) y pinta el recuadro de arranque. */
@Configuration
public class TrazaConfig implements WebMvcConfigurer {

    private final int puerto;
    private final String iaUrl;

    public TrazaConfig(@Value("${app.trazas.color:true}") boolean color,
                       @Value("${server.port:8080}") int puerto,
                       @Value("${ia.url}") String iaUrl) {
        Traza.activarColor(color);
        this.puerto = puerto;
        this.iaUrl = iaUrl;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TrazaInterceptor()).addPathPatterns("/api/**");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void listo() {
        Traza.listo(puerto, iaUrl);
    }
}
