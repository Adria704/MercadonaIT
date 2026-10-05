# Demo "solo backend": lanza las peticiones una a una mientras la consola de Spring muestra el recorrido.
# Requisitos: PostgreSQL, servicio de IA (puerto 8001) y backend (puerto 8080) arrancados.
# Uso (en otra ventana de PowerShell, desde la carpeta backend):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\demo-backend.ps1              -> pausa antes de cada paso (para ir contándolo)
#   .\demo-backend.ps1 -SinPausas   -> todo seguido
param([string]$Api = "http://localhost:8080/api", [switch]$SinPausas)

$script:n = 0
$TOTAL = 8
$ANCHO = 74

function Llamar([string]$Metodo, [string]$Ruta, $Cuerpo = $null) {
    $p = @{ Method = $Metodo; Uri = "$Api$Ruta"; UseBasicParsing = $true }
    if ($null -ne $Cuerpo) {
        $p.Body = [System.Text.Encoding]::UTF8.GetBytes(($Cuerpo | ConvertTo-Json -Depth 6 -Compress))
        $p.ContentType = "application/json; charset=utf-8"
    }
    $r = Invoke-WebRequest @p
    return ([System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json)
}

function Paso([string]$Titulo, [string]$Ruta) {
    $script:n++
    Write-Host ""
    Write-Host (" " + ("-" * $ANCHO)) -ForegroundColor DarkGray
    Write-Host " " -NoNewline
    Write-Host (" {0}/{1} " -f $script:n, $TOTAL) -ForegroundColor Black -BackgroundColor Yellow -NoNewline
    Write-Host "  $Titulo" -ForegroundColor White
    if ($Ruta) { Write-Host "        $Ruta" -ForegroundColor DarkCyan }
    Write-Host (" " + ("-" * $ANCHO)) -ForegroundColor DarkGray
    if (-not $SinPausas) { Read-Host "   Enter para lanzarlo" | Out-Null }
}

function Dato([string]$Etiqueta, [string]$Valor, [string]$Color = "Cyan") {
    Write-Host ("   {0,-16}" -f $Etiqueta) -ForegroundColor $Color -NoNewline
    Write-Host " $Valor"
}

function Bien([string]$Texto) { Write-Host "   [OK] " -ForegroundColor Green -NoNewline; Write-Host $Texto }
function Fallo($e) { Write-Host "   [ERROR] $($e.Exception.Message)" -ForegroundColor Red }

function Ticket($cesta) {
    $w = 46
    Write-Host ""
    Write-Host ("   +" + ("-" * $w) + "+") -ForegroundColor DarkGray
    Write-Host ("   |" + ("DONA".PadLeft(25)).PadRight($w) + "|") -ForegroundColor Green
    Write-Host ("   |" + (("Cesta para {0}" -f $cesta.personas).PadLeft(29)).PadRight($w) + "|") -ForegroundColor DarkGray
    Write-Host ("   |" + ("-" * $w) + "|") -ForegroundColor DarkGray
    foreach ($l in $cesta.lineas) {
        $nombre = $l.nombre; if ($nombre.Length -gt 31) { $nombre = $nombre.Substring(0, 30) + "." }
        Write-Host ("   | {0,2}x {1,-31} {2,7:N2} |" -f $l.cantidad, $nombre, $l.subtotal)
    }
    Write-Host ("   |" + ("-" * $w) + "|") -ForegroundColor DarkGray
    Write-Host ("   | {0,-35} {1,8:N2} |" -f "Presupuesto", $cesta.presupuesto) -ForegroundColor DarkGray
    Write-Host ("   | {0,-35} {1,8:N2} |" -f "TOTAL", $cesta.total) -ForegroundColor Yellow
    Write-Host ("   | {0,-35} {1,8:N2} |" -f "Te sobran", $cesta.sobra) -ForegroundColor Green
    Write-Host ("   +" + ("-" * $w) + "+") -ForegroundColor DarkGray
    if ($cesta.restricciones) { Dato "Apta para" ($cesta.restricciones -join ", ") "Green" }
}

# ------------------------------------------------------------------ portada
Write-Host ""
Write-Host "     ____                    " -ForegroundColor Green
Write-Host "    |  _ \  ___  _ __   __ _ " -ForegroundColor Green
Write-Host "    | | | |/ _ \| '_ \ / _`` |" -ForegroundColor Green
Write-Host "    | |_| | (_) | | | | (_| |" -ForegroundColor Green
Write-Host "    |____/ \___/|_| |_|\__,_|" -ForegroundColor Green
Write-Host "    no te abandona  -  demo del backend" -ForegroundColor Gray
Write-Host ""
Write-Host "    API: $Api" -ForegroundColor DarkGray
Write-Host "    Mira la ventana de Spring: cada paso deja su recorrido." -ForegroundColor DarkGray

# ------------------------------------------------------------------ pasos
Paso "Estado del backend y del servicio de IA" "GET /api/status  +  GET /api/ia/estado"
try {
    $s = Llamar GET "/status"; Bien $s.status
    $e = Llamar GET "/ia/estado"
    Dato "Modelos" ($e.proveedores_disponibles -join ", ")
    Dato "Recomendador" $e.recomendador
    Dato "Base de datos" $e.base_de_datos
} catch { Fallo $_ }

Paso "Login con el telefono (como el ticket digital)" "POST /api/clientes/login"
try { $c = Llamar POST "/clientes/login" @{ telefono = "600111222" }; Bien "Cliente $($c.id): $($c.nombre)" } catch { Fallo $_ }

Paso "Recomendacion personalizada" "POST /api/tickets/C0001/recomendacion"
try {
    $r = Llamar POST "/tickets/C0001/recomendacion"
    Dato "Aprendizaje" $r.adaptacion.mensaje "Magenta"
    foreach ($x in ($r.lo_de_siempre | Where-Object { $_.toca_reponer })) { Dato "Toca reponer" "$($x.nombre)  ($($x.motivo))" "Yellow" }
    foreach ($x in ($r.para_ti | Select-Object -First 3)) { Dato "Para ti" "$($x.nombre)  ($($x.motivo))" }
    foreach ($x in ($r.descubre | Select-Object -First 2)) { Dato "Descubre" "$($x.nombre)  ($($x.motivo))" "DarkCyan" }
} catch { Fallo $_ }

Paso "Llega un ticket digital (pago en efectivo, foto del ticket)" "POST /api/tickets"
$fecha = Get-Date -Format "yyyy-MM-ddTHH:mm:00"
$ticket = @{ cliente_id = "C0001"; tienda_id = "T02"; fecha = $fecha; metodo_pago = "efectivo"; origen = "foto";
             lineas = @(@{ producto_id = "P0001"; cantidad = 2 }, @{ producto_id = "P0037"; cantidad = 1 }) }
try { $t = Llamar POST "/tickets" $ticket; Bien "Guardado $($t.ticket_id): $($t.lineas) lineas, $($t.total) EUR" } catch { Fallo $_ }

Paso "El mismo ticket otra vez (tarjeta + foto del mismo ticket)" "POST /api/tickets  (repetido)"
try {
    $t2 = Llamar POST "/tickets" $ticket
    if ($t2.duplicado) { Write-Host "   [DEDUPLICADO] $($t2.mensaje)" -ForegroundColor Yellow } else { Bien "Guardado $($t2.ticket_id)" }
} catch { Fallo $_ }

Paso "Historial de tickets del cliente" "GET /api/tickets/C0001"
try {
    $h = @(Llamar GET "/tickets/C0001")
    Dato "Tickets" "$($h.Count) recuperados de PostgreSQL"
    foreach ($x in ($h | Select-Object -First 3)) { Dato ($x.fecha.Substring(0, 16).Replace("T", " ")) ("{0,7:N2} EUR  {1} productos  ({2})" -f $x.total, @($x.lineas).Count, $x.origen) "DarkGray" }
} catch { Fallo $_ }

Paso "Dona llena la cesta" "POST /api/clientes/C0001/chat  ->  '30 € para una persona celíaca y dos veganas'"
try {
    $d = Llamar POST "/clientes/C0001/chat" @{ mensaje = "30 € para una persona celíaca y dos veganas" }
    Dato "Dona" $d.respuesta "Magenta"
    Dato "Herramientas" (($d.traza | Where-Object { $_.tipo -eq "herramienta" } | ForEach-Object { $_.nombre }) -join ", ")
    $cesta = ($d.traza | Where-Object { $_.cesta } | Select-Object -First 1).cesta
    if ($cesta) { Ticket $cesta }
} catch { Fallo $_ }

Paso "Cliente nuevo sin compras: recomienda por sus gustos iniciales" "GET /api/clientes/C0003/recomendaciones"
try {
    $nv = Llamar GET "/clientes/C0003/recomendaciones"
    Dato "Aprendizaje" $nv.adaptacion.mensaje "Magenta"
    foreach ($x in ($nv.para_ti | Select-Object -First 4)) { Dato "Para ti" "$($x.nombre)  ($($x.motivo))" }
} catch { Fallo $_ }

Write-Host ""
Write-Host (" " + ("=" * $ANCHO)) -ForegroundColor Green
Write-Host "   Fin de la demo." -ForegroundColor Green
Write-Host (" " + ("=" * $ANCHO)) -ForegroundColor Green
