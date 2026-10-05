package com.example.demo.config;

import java.util.List;
import java.util.Map;

/** Utilidades para leer cuerpos JSON aceptando claves en snake_case o camelCase. */
public final class Json {
    private Json() {
    }

    public static String texto(Map<String, Object> m, String snake, String camel) {
        Object v = m.containsKey(snake) ? m.get(snake) : m.get(camel);
        return v == null ? null : v.toString();
    }

    public static Integer entero(Map<String, Object> m, String snake, String camel) {
        Object v = m.containsKey(snake) ? m.get(snake) : m.get(camel);
        return v instanceof Number n ? n.intValue() : (v == null ? null : Integer.valueOf(v.toString()));
    }

    public static Double decimal(Map<String, Object> m, String snake, String camel) {
        Object v = m.containsKey(snake) ? m.get(snake) : m.get(camel);
        return v instanceof Number n ? n.doubleValue() : (v == null ? null : Double.valueOf(v.toString()));
    }

    @SuppressWarnings("unchecked")
    public static List<Object> lista(Map<String, Object> m, String clave) {
        Object v = m.get(clave);
        return v instanceof List<?> l ? (List<Object>) l : List.of();
    }
}
