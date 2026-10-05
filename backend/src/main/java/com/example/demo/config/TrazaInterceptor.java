package com.example.demo.config;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

/** Pinta la cabecera y el pie (codigo + tiempo) de cada peticion a /api en la consola. */
public class TrazaInterceptor implements HandlerInterceptor {

    private static final String INICIO = "traza.inicio";

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if ("OPTIONS".equals(request.getMethod())) {
            return true;  // peticiones previas de CORS: no aportan nada en la demo
        }
        request.setAttribute(INICIO, System.currentTimeMillis());
        String query = request.getQueryString();
        Traza.inicio(request.getMethod(), request.getRequestURI() + (query == null ? "" : "?" + query));
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        Object inicio = request.getAttribute(INICIO);
        if (inicio instanceof Long t0) {
            Traza.fin(response.getStatus(), System.currentTimeMillis() - t0);
        }
    }
}
