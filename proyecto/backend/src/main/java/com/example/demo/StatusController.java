package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/api/status")
    public String getStatus() {
        return "{\"status\": \"Backend de Spring Boot Operativo\"}";
    }
}