package com.example.demo.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** Permite que el frontend React (en otro puerto) llame a la API. */
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Value("${app.cors.origenes}")
    private String[] origenes;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(origenes)
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS");
    }
}
