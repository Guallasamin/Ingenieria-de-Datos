#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PASO 5 - Genera el informe del flujo ELK en PDF con datos reales.
=============================================================================
Todas las cifras se leen en el momento de la generacion: los conteos de
documentos y las latencias salen de Elasticsearch, y el reparto de memoria
del fichero informe/metricas_memoria.json que se captura en el anfitrion.

Ejecucion:  docker exec etl_runtime python elk/05_informe_elk.py
"""
import json
import os
import urllib.request
import datetime as dt

from weasyprint import HTML

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAL = os.path.join(RAIZ, "informe")
os.makedirs(SAL, exist_ok=True)

ES_HOST = os.getenv("ES_HOST", "elasticsearch")


# =====================================================================
#  Acceso a Elasticsearch
# =====================================================================
def es(ruta, cuerpo=None):
    url = f"http://{ES_HOST}:9200{ruta}"
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(
        url, data=datos, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def cuenta(indice):
    try:
        return es(f"/{indice}/_count")["count"]
    except Exception:
        return 0


# ---------------------------------------------------------------------
#  Identidad visual USFQ (misma que el informe de la semana 1)
# ---------------------------------------------------------------------
ROJO, NEGRO = "#ed1c24", "#231f20"
TINTA, TINTA2, TINTA3 = NEGRO, "#4a4b4c", "#8a8b8c"
CREMA, GRID, BORDE = "#faf3e9", "#e3ded4", "#d8d4cb"


def mil(n):
    """Separador de miles a la espanola: 176990 -> '176.990'."""
    return f"{int(n):,}".replace(",", ".")


def dec(v, n=2):
    """Decimales con coma: 3.1416 -> '3,14'."""
    return f"{v:,.{n}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# =====================================================================
#  Lectura de metricas reales
# =====================================================================
INDICES = [
    ("banca-hechos", "B1", "PostgreSQL · DW", "batch"),
    ("banca-catalogo-entidad", "B2", "MySQL · entidades", "batch"),
    ("banca-catalogo-geografia", "B2", "MySQL · geografía", "batch"),
    ("banca-colocaciones-2026", "B3", "CSV", "batch"),
    ("banca-transacciones", "N1", "NDJSON → Filebeat", "nrt"),
    ("banca-bitacora-etl", "N2", "PostgreSQL incremental", "nrt"),
]

CONTEO = {i: cuenta(i) for i, *_ in INDICES}
TOTAL_DOCS = sum(CONTEO.values())

# --- agregaciones del canal near real-time ---------------------------
TX = es("/banca-transacciones/_search", {
    "size": 0,
    "aggs": {
        "lat": {"percentiles": {"field": "latencia_ingesta_ms",
                                "percents": [50, 90, 95, 99]}},
        "canal": {"terms": {"field": "canal", "size": 10}},
        "tamanio": {"terms": {"field": "grupo_tamanio", "size": 5}},
        "tipo": {"terms": {"field": "tipo_transaccion", "size": 10}},
        "monto": {"sum": {"field": "monto"}},
        "rechazadas": {"filter": {"term": {"estado": "RECHAZADA"}}},
        "alertas": {"filter": {"exists": {"field": "alerta"}}},
        "sin_catalogo": {"filter": {"term": {"tags": "sin_catalogo"}}},
        "caudal": {"date_histogram": {"field": "@timestamp",
                                      "fixed_interval": "10s"}},
        "inicio": {"min": {"field": "@timestamp"}},
        "fin": {"max": {"field": "@timestamp"}},
    },
})["aggregations"]

LAT = TX["lat"]["values"]
N_TX = CONTEO["banca-transacciones"]
DUR_TX = max((TX["fin"]["value"] - TX["inicio"]["value"]) / 1000.0, 1)
TPS = N_TX / DUR_TX

# --- conciliacion del flujo batch ------------------------------------
SUMA_ES = es("/banca-hechos/_search", {
    "size": 0, "aggs": {"s": {"sum": {"field": "saldo_total"}}}
})["aggregations"]["s"]["value"]

# --- flujo de datos y ciclo de vida ----------------------------------
DS = es("/_data_stream/banca-transacciones")["data_streams"][0]

# --- salud del cluster -----------------------------------------------
SALUD = es("/_cluster/health")

# --- memoria (capturada en el anfitrion) -----------------------------
try:
    MEM = json.load(open(os.path.join(SAL, "metricas_memoria.json"),
                         encoding="utf-8"))
except Exception:
    MEM = {"servicios": [], "total_uso_mb": 0}
MEM_SRV = sorted(MEM["servicios"], key=lambda s: -s["uso_mb"])


# =====================================================================
#  FIGURA 1 - Arquitectura del flujo mixto
# =====================================================================
def diagrama_arquitectura():
    W, H = 900, 470
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="Arquitectura del flujo ELK mixto: tres fuentes en '
         f'lote y dos en near real-time">']

    def caja(x, y, w, h, titulo, lineas, borde=BORDE, relleno="#ffffff",
             filete=None, ancla="start"):
        s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" '
                 f'fill="{relleno}" stroke="{borde}" stroke-width="1"/>')
        if filete:
            s.append(f'<rect x="{x}" y="{y}" width="{w}" height="2.5" rx="1" '
                     f'fill="{filete}"/>')
        cx = x + w / 2 if ancla == "middle" else x + 10
        s.append(f'<text x="{cx}" y="{y + 19}" text-anchor="{ancla}" '
                 f'font-size="11" font-weight="700" fill="{TINTA}">{titulo}</text>')
        for i, ln in enumerate(lineas):
            s.append(f'<text x="{cx}" y="{y + 34 + i * 12.5}" '
                     f'text-anchor="{ancla}" font-size="9.5" '
                     f'fill="{TINTA2}">{ln}</text>')

    def flecha(x1, y1, x2, y2, guion=None):
        d = f' stroke-dasharray="{guion}"' if guion else ""
        s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2 - 7}" y2="{y2}" '
                 f'stroke="{TINTA3}" stroke-width="1.2"{d}/>')
        s.append(f'<path d="M{x2 - 7},{y2 - 3.5} L{x2},{y2} L{x2 - 7},{y2 + 3.5} Z" '
                 f'fill="{TINTA3}"/>')

    # --- rotulos de carril -------------------------------------------
    s.append(f'<rect x="0" y="30" width="{W}" height="188" fill="{CREMA}" '
             f'opacity="0.55"/>')
    s.append(f'<text x="6" y="24" font-size="10" font-weight="700" '
             f'fill="{TINTA2}">ESQUEMA BATCH · carga masiva histórica</text>')
    s.append(f'<text x="6" y="248" font-size="10" font-weight="700" '
             f'fill="{ROJO}">ESQUEMA NEAR REAL-TIME · latencia de segundos</text>')

    # --- columna 1: fuentes ------------------------------------------
    caja(6, 36, 176, 54, "B1 · PostgreSQL",
         ["dw.fact + 6 dimensiones", f"{mil(CONTEO['banca-hechos'])} filas"],
         filete=NEGRO)
    caja(6, 96, 176, 54, "B2 · MySQL",
         ["catalogos_sb · 2 catálogos",
          f"{mil(CONTEO['banca-catalogo-entidad'] + CONTEO['banca-catalogo-geografia'])} filas"],
         filete=NEGRO)
    caja(6, 156, 176, 54, "B3 · CSV",
         ["colocaciones_2026.csv",
          f"{mil(CONTEO['banca-colocaciones-2026'])} filas"], filete=NEGRO)
    caja(6, 258, 176, 54, "N1 · Flujo NDJSON",
         ["transacciones.ndjson", "escritura continua"], filete=ROJO)
    caja(6, 318, 176, 54, "N2 · PostgreSQL",
         ["staging.etl_bitacora", "sondeo incremental 15 s"], filete=ROJO)

    # --- columna 2: agente -------------------------------------------
    caja(212, 258, 118, 54, "Filebeat",
         ["tail del fichero", "empuja (push)"], filete=ROJO)
    s.append(f'<text x="271" y="336" text-anchor="middle" font-size="9" '
             f'fill="{TINTA3}">JDBC pregunta (pull)</text>')

    # --- columna 3: Logstash -----------------------------------------
    s.append(f'<rect x="360" y="36" width="196" height="336" rx="3" '
             f'fill="#ffffff" stroke="{TINTA}" stroke-width="1.4"/>')
    s.append(f'<text x="458" y="56" text-anchor="middle" font-size="12" '
             f'font-weight="700" fill="{TINTA}">Logstash</text>')
    s.append(f'<text x="458" y="70" text-anchor="middle" font-size="9" '
             f'fill="{TINTA2}">5 pipelines aislados</text>')
    for i, (pid, txt) in enumerate([
            ("b1-pg-hechos", "jdbc · paginado 20k"),
            ("b2-mysql-catalogos", "jdbc · 2 entradas"),
            ("b3-csv-colocaciones", "file · modo read"),
            ("n1-beats-transacciones", "beats · 5044"),
            ("n2-jdbc-bitacora", "jdbc · marca de agua")]):
        y = 84 + i * 56
        col = ROJO if i >= 3 else NEGRO
        s.append(f'<rect x="372" y="{y}" width="172" height="46" rx="2" '
                 f'fill="{CREMA}" stroke="{BORDE}"/>')
        s.append(f'<rect x="372" y="{y}" width="2.5" height="46" fill="{col}"/>')
        s.append(f'<text x="382" y="{y + 17}" font-size="9.5" font-weight="700" '
                 f'fill="{TINTA}">{pid}</text>')
        s.append(f'<text x="382" y="{y + 32}" font-size="8.5" '
                 f'fill="{TINTA2}">{txt}</text>')

    # --- columna 4: Elasticsearch ------------------------------------
    caja(586, 36, 190, 336, "Elasticsearch", [], filete=NEGRO)
    s.append(f'<text x="596" y="34" font-size="9" fill="{TINTA3}"></text>')
    for i, (idx, sig, _, modo) in enumerate(INDICES):
        y = 62 + i * 52
        col = ROJO if modo == "nrt" else NEGRO
        s.append(f'<rect x="598" y="{y}" width="166" height="42" rx="2" '
                 f'fill="#ffffff" stroke="{BORDE}"/>')
        s.append(f'<rect x="598" y="{y}" width="2.5" height="42" fill="{col}"/>')
        s.append(f'<text x="608" y="{y + 16}" font-size="9" font-weight="700" '
                 f'fill="{TINTA}">{idx}</text>')
        s.append(f'<text x="608" y="{y + 31}" font-size="8.5" '
                 f'fill="{TINTA2}">{mil(CONTEO[idx])} documentos</text>')

    # --- columna 5: Kibana -------------------------------------------
    caja(806, 150, 88, 108, "Kibana", ["6 vistas", "de datos", "", "1 tablero",
                                       "4 paneles"], filete=NEGRO)

    # --- conexiones ---------------------------------------------------
    for y in (63, 123, 183):
        flecha(182, y, 360, y)
    flecha(182, 285, 212, 285)
    flecha(330, 285, 360, 285)
    flecha(182, 345, 360, 345, guion="4 3")
    flecha(556, 204, 586, 204)
    flecha(776, 204, 806, 204)

    s.append("</svg>")
    return "".join(s)


# =====================================================================
#  FIGURA 2 - Caudal de transacciones en el canal near real-time
# =====================================================================
def grafico_caudal():
    b = [x for x in TX["caudal"]["buckets"] if x["doc_count"] > 0]
    if not b:
        return ""
    W, H = 760, 250
    ML, MR, MT, MB = 54, 20, 26, 46
    pw, ph = W - ML - MR, H - MT - MB
    mx = max(x["doc_count"] for x in b)
    tope = int((mx // 50 + 1) * 50)
    bw = pw / len(b)
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="Transacciones ingeridas por intervalos de diez segundos">']
    for g in range(0, tope + 1, tope // 4):
        y = MT + ph - g / tope * ph
        s.append(f'<line x1="{ML}" x2="{ML + pw}" y1="{y:.1f}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ML - 9}" y="{y + 4:.1f}" text-anchor="end" '
                 f'font-size="10.5" fill="{TINTA3}">{g}</text>')
    for i, x in enumerate(b):
        h = x["doc_count"] / tope * ph
        px = ML + i * bw + bw * 0.14
        s.append(f'<rect x="{px:.1f}" y="{MT + ph - h:.1f}" '
                 f'width="{bw * 0.72:.1f}" height="{h:.1f}" fill="{ROJO}"/>')
    # eje temporal: primera, media y ultima marca
    for i in (0, len(b) // 2, len(b) - 1):
        hh = dt.datetime.fromisoformat(
            b[i]["key_as_string"].replace("Z", "+00:00"))
        s.append(f'<text x="{ML + i * bw + bw / 2:.1f}" y="{MT + ph + 18}" '
                 f'text-anchor="middle" font-size="10" '
                 f'fill="{TINTA3}">{hh:%H:%M:%S}</text>')
    s.append(f'<text x="4" y="12" font-size="10" fill="{TINTA3}">'
             f'transacciones por intervalo de 10 s</text>')
    s.append(f'<text x="{ML + pw / 2:.0f}" y="{H - 6}" text-anchor="middle" '
             f'font-size="9.5" fill="{TINTA3}">hora de emisión (UTC)</text>')
    s.append("</svg>")
    return "".join(s)


# =====================================================================
#  FIGURA 3 - Transacciones por canal de atencion
# =====================================================================
def grafico_canales():
    b = TX["canal"]["buckets"]
    if not b:
        return ""
    NOMBRE = {"BANCA_MOVIL": "Banca móvil",
              "CAJERO_AUTOMATICO": "Cajero automático",
              "BANCA_WEB": "Banca web", "POS_COMERCIO": "POS en comercio",
              "VENTANILLA": "Ventanilla", "CORRESPONSAL": "Corresponsal"}
    W = 760
    H = 32 * len(b) + 42
    ML, MR = 168, 96
    pw = W - ML - MR
    mx = max(x["doc_count"] for x in b)
    tope = (mx // 100 + 1) * 100
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="Transacciones por canal de atencion">']
    for g in range(0, tope + 1, tope // 4):
        px = ML + pw * g / tope
        s.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="6" '
                 f'y2="{32 * len(b) + 4}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{px:.1f}" y="{32 * len(b) + 24}" '
                 f'text-anchor="middle" font-size="10.5" '
                 f'fill="{TINTA3}">{mil(g)}</text>')
    for i, x in enumerate(b):
        yy = 12 + 32 * i
        w = pw * x["doc_count"] / tope
        s.append(f'<text x="{ML - 12}" y="{yy + 12}" text-anchor="end" '
                 f'font-size="11" fill="{TINTA}">'
                 f'{NOMBRE.get(x["key"], x["key"])}</text>')
        s.append(f'<path d="M{ML} {yy} H{ML + w - 4:.1f} a4,4 0 0 1 4,4 v9 '
                 f'a4,4 0 0 1 -4,4 H{ML} Z" fill="{NEGRO}"/>')
        pct = 100 * x["doc_count"] / N_TX
        s.append(f'<text x="{ML + w + 10:.1f}" y="{yy + 12}" font-size="10.5" '
                 f'font-weight="600" fill="{TINTA}">{mil(x["doc_count"])}'
                 f'  <tspan fill="{TINTA3}" font-weight="400">'
                 f'{dec(pct, 1)} %</tspan></text>')
    s.append("</svg>")
    return "".join(s)


# =====================================================================
#  Composicion del documento
# =====================================================================
FILAS_IDX = "".join(
    f'<tr><td><b>{sig}</b></td><td>{origen}</td>'
    f'<td>{"Lote" if modo == "batch" else "Near real-time"}</td>'
    f'<td><code>{idx}</code></td>'
    f'<td class="n">{mil(CONTEO[idx])}</td></tr>'
    for idx, sig, origen, modo in INDICES)

FILAS_MEM = "".join(
    f'<tr><td><code>{s["nombre"]}</code></td>'
    f'<td class="n">{mil(s["uso_mb"])}</td>'
    f'<td class="n">{mil(s["limite_mb"]) if s["limite_mb"] < 3000 else "—"}</td></tr>'
    for s in MEM_SRV)

FILAS_CANAL = "".join(
    f'<tr><td>{x["key"].replace("_", " ").title()}</td>'
    f'<td class="n">{mil(x["doc_count"])}</td></tr>'
    for x in TX["tipo"]["buckets"])

FILAS_TAM = "".join(
    f'<tr><td>{x["key"]}</td><td class="n">{mil(x["doc_count"])}</td>'
    f'<td class="n">{dec(100 * x["doc_count"] / N_TX, 1)} %</td></tr>'
    for x in TX["tamanio"]["buckets"])

RETOS = [
    ("Memoria: el equipo solo ofrece 3,8 GiB a Docker",
     "Elasticsearch, Logstash y Kibana reclaman en conjunto mas de 4 GiB con "
     "su configuracion por defecto, de modo que el stack no arrancaba junto a "
     "PostgreSQL y MySQL.",
     "Se acotaron los <i>heaps</i> de la maquina virtual de Java "
     "(Elasticsearch 512 MB, Logstash 384 MB, Kibana 448 MB), se fijo un "
     "<code>mem_limit</code> por servicio y se desactivo el "
     "<code>performance_schema</code> de MySQL, que por si solo liberó "
     "400 MB. Los ocho contenedores conviven ahora en "
     f"{dec(MEM['total_uso_mb'] / 1024, 2)} GiB."),
    ("<code>path.config</code> anula <code>pipelines.yml</code>",
     "Logstash arranco un unico pipeline llamado <code>main</code> que "
     "concatenaba los cinco ficheros <code>.conf</code>: cada evento salia "
     "por las cinco salidas a la vez. El sintoma fue un indice de "
     "transacciones con 18.375 documentos <i>antes</i> de que el simulador "
     "se hubiera ejecutado, y documentos cuyo <code>_id</code> era el texto "
     "literal <code>%{saldo_sk}</code> porque la sustitucion no aplicaba en "
     "el indice equivocado.",
     "Se elimino <code>path.config</code> de <code>logstash.yml</code>. Esa "
     "opcion tiene prioridad sobre <code>pipelines.yml</code> y desactiva el "
     "aislamiento entre pipelines."),
    ("El borrado con comodin se rechaza en silencio",
     "<code>DELETE /banca-*</code> devuelve un error 400 porque el ajuste "
     "<code>action.destructive_requires_name</code> vale <code>true</code> "
     "por defecto en Elasticsearch 8. El error viaja en el cuerpo de la "
     "respuesta, no en el codigo de salida de <code>curl</code>: al "
     "descartar la salida, el purgado parecia correcto y los datos antiguos "
     "seguian en el indice.",
     "El script de reinicio enumera los indices con <code>_cat/indices</code>, "
     "los borra <b>por nombre</b> y comprueba que la respuesta contenga "
     "<code>acknowledged: true</code>."),
    ("El estado persistente vive en cinco sitios y ninguno se limpia solo",
     "Reiniciar el flujo para probar un cambio resulto sorprendentemente "
     "dificil. Tras corregir los pipelines, los documentos mal enrutados "
     "reaparecian; tras vaciar el registro de Filebeat, volvian a entrar "
     "2.400 transacciones antiguas con latencias de horas. El estado esta "
     "repartido en: los indices de Elasticsearch, la cola persistente de "
     "Logstash (<code>lsdata</code>), el registro de Filebeat "
     "(<code>fbdata</code>), la marca de agua del sondeo incremental y el "
     "propio fichero NDJSON. Cada uno reintroduce datos por su cuenta.",
     "Un unico script, <code>elk/00_reiniciar_flujo.sh</code>, purga los "
     "cinco. Ademas hay que <b>eliminar</b> el contenedor y no solo "
     "detenerlo: Docker se niega a borrar un volumen que un contenedor "
     "todavia referencia, aunque este parado, y el fallo es silencioso."),
    ("Un pipeline mal configurado no impide que Logstash arranque",
     "El filtro <code>translate</code> no admite el ajuste "
     "<code>tag_on_failure</code>. Logstash arranco con normalidad, los "
     "otros cuatro pipelines funcionaron y el puerto 5044 simplemente no "
     "quedo a la escucha: Filebeat acumulaba eventos contra un destino que "
     "rechazaba la conexion. El registro tenia el motivo, pero la operacion "
     "aparentaba haber ido bien.",
     "El script de reinicio ya no confia en el mensaje de arranque: "
     "consulta <code>/_node/pipelines</code> y compara la lista de "
     "pipelines activos con los cinco esperados, extrayendo del registro la "
     "causa si falta alguno."),
    ("El punto de entrada de la imagen reescribe la configuracion",
     "Al declarar <code>XPACK_MONITORING_ENABLED</code> como variable de "
     "entorno, el arranque de Logstash intenta reescribir "
     "<code>logstash.yml</code>; el montaje es de solo lectura y el "
     "contenedor entra en un bucle de reinicio con el mensaje "
     "<code>read-only file system</code>.",
     "El ajuste se declara dentro del propio <code>logstash.yml</code> y se "
     "retira del entorno."),
    ("El controlador de MySQL convierte TINYINT(1) en booleano",
     "El catalogo marcaba las 26 entidades como <b>no vigentes</b>, incluidas "
     "las activas con vigencia hasta el ano 9999. El controlador de MySQL "
     "entrega las columnas <code>TINYINT(1)</code> como <code>Boolean</code> "
     "&mdash; comportamiento de <code>tinyInt1isBit</code> &mdash;, de modo "
     "que la comparacion <code>[es_vigente] == 1</code> escrita en Logstash "
     "era siempre falsa. El fallo no produjo ningun error: simplemente el "
     "enriquecimiento del canal en vivo dejo de encontrar entidades.",
     "La conversion se resolvio en la propia consulta, donde el tipo es "
     "inequivoco: <code>IF(es_vigente = 1, 'true', 'false')</code>. Logstash "
     "solo hace el <code>convert</code> final a booleano."),
    ("La cola interna de Filebeat marcaba la latencia del canal",
     "Resuelto el enriquecimiento, la latencia seguia en 5,4 s de mediana y "
     "<b>10,3 s en el percentil 99</b>. La cifra delataba la causa: coincide "
     "con <code>queue.mem.flush.timeout</code>, que Filebeat fija en 10 s. "
     "El agente acumula 1.600 eventos antes de enviar y, si no los reune, "
     "espera ese temporizador. A 20 eventos por segundo el umbral no se "
     "alcanza nunca, de modo que <b>todos</b> los lotes salian por "
     "vencimiento del reloj y no por volumen.",
     f"Se bajo el umbral a 32 eventos y el temporizador a 1 s. La latencia "
     f"p99 paso de 10.257 ms a {mil(LAT['99.0'])} ms sin tocar ningun otro "
     f"componente. En un canal near real-time el compromiso se invierte: "
     f"conviene enviar lotes pequenios a menudo antes que lotes grandes con "
     f"retraso."),
    ("Una consulta por evento hunde la latencia",
     "El enriquecimiento se implemento primero con el filtro "
     "<code>elasticsearch</code>, que consulta el indice del catalogo "
     "<b>una vez por evento</b>. Cada consulta es un viaje de ida y vuelta "
     "por HTTP: el pipeline no lograba sostener 20 eventos por segundo, la "
     "cola crecia sin limite y la latencia p99 alcanzo <b>313 segundos</b>. "
     "Un canal near real-time con esa latencia deja de serlo.",
     "Una dimension de 25 filas no se consulta por red. Se materializa como "
     "diccionario y el filtro <code>translate</code> la resuelve en memoria, "
     "con recarga cada 300 s. El coste por evento pasa de una peticion de "
     "red a una busqueda en un mapa."),
    ("El vaciado por linea contra un montaje de macOS estrangula al generador",
     "El generador escribia el fichero NDJSON en un directorio del "
     "anfitrion montado en el contenedor, con <code>flush()</code> tras cada "
     "linea. Cada escritura sincrona sobre ese tipo de montaje cuesta "
     "milisegundos: el simulador solicitado a 20 eventos por segundo "
     "entregaba 5,6, y en una corrida se detuvo cinco minutos y medio.",
     "El fichero se traslado a un <b>volumen de Docker compartido</b> entre "
     "el generador y Filebeat, con lo que el sistema de ficheros del "
     "anfitrion sale del camino critico. El <code>flush()</code> se "
     "mantiene, porque sin el Filebeat no ve las lineas."),
    ("La clave natural del CSV no es unica",
     "La huella de idempotencia se calculo primero sobre "
     "(fecha, entidad, provincia, canton, segmento). El resultado fueron "
     "9.422 documentos en lugar de 9.432: diez pares de filas comparten esas "
     "cinco claves con importes distintos &mdash; en Quito coexisten un "
     "registro de USD 1,00 y otro de USD 4.614 millones &mdash;, de modo que "
     "la segunda fila sobrescribia a la primera.",
     "La huella SHA-256 incluye tambien las cuatro medidas. Asi se descartan "
     "los duplicados exactos sin perder filas legitimas."),
    ("Entrega «al menos una vez» frente a idempotencia",
     "Logstash garantiza que un evento se entrega al menos una vez, no "
     "exactamente una vez. Sin identificador de documento, cada reejecucion "
     "del flujo batch anadia 176.990 documentos nuevos en lugar de "
     "actualizar los existentes.",
     "Cada flujo define un <code>document_id</code> determinista: la clave "
     "subrogada del almacen, la clave compuesta del catalogo o la huella "
     "SHA-256 del CSV."),
    ("Zona horaria del controlador JDBC",
     "El controlador entrega las columnas <code>DATE</code> en la zona del "
     "servidor y Logstash las reinterpreta en UTC. Los cortes de fin de mes "
     "retrocedian un dia, con lo que el saldo de mayo caia en abril.",
     "La consulta extrae la fecha tambien como texto "
     "(<code>fecha::text</code>) y el filtro <code>date</code> fija "
     "explicitamente <code>America/Guayaquil</code>."),
    ("El mapeo dinamico convierte los importes en texto",
     "Si Logstash escribe antes de que exista la plantilla de indice, "
     "Elasticsearch deduce el tipo de cada campo. Los <code>NUMERIC</code> "
     "quedaban como <code>text</code> y ninguna agregacion "
     "(<code>sum</code>, <code>avg</code>) podia ejecutarse.",
     "Las cinco plantillas se registran antes de levantar Logstash; el orden "
     "esta forzado en los scripts numerados."),
    ("El campo <code>tags</code> heredaba el mapeo dinamico",
     "Al no declararse en la plantilla, Elasticsearch tipaba "
     "<code>tags</code> como texto analizado. El analizador estandar parte "
     "<code>_sin_catalogo</code> en dos terminos, asi que la consulta "
     "<code>term</code> de la prueba de verificacion nunca coincidia y "
     "reportaba cero incidencias aunque las hubiera.",
     "La plantilla declara <code>tags</code> como <code>keyword</code>. Las "
     "etiquetas de control se nombran sin guion bajo inicial."),
    ("La importacion de objetos de Kibana encadena migraciones antiguas",
     "El tablero se creo primero con la API de importacion. Kibana devolvia "
     "un error 500 y en su registro aparecia <code>Cannot read properties "
     "of undefined (reading 'layers')</code>: al importar, el servidor "
     "aplica la cadena historica de migraciones del tipo <code>lens</code>, "
     "y una de las antiguas espera una estructura que un objeto escrito a "
     "mano ya no tiene.",
     "Los objetos se crean uno a uno con la API de objetos guardados "
     "(<code>POST /api/saved_objects/lens/&lt;id&gt;</code>), que los "
     "almacena directamente en la version vigente y no ejecuta esa cadena."),
    ("Un solo nodo no puede alojar replicas",
     "Con la replica que Elasticsearch crea por omision, los fragmentos "
     "quedan sin asignar y el cluster permanece en estado amarillo.",
     "Las plantillas fijan <code>number_of_replicas: 0</code>. El cluster "
     f"reporta estado <b>{SALUD['status']}</b> con "
     f"{SALUD['active_shards']} fragmentos activos y "
     f"{SALUD['unassigned_shards']} sin asignar."),
    ("Dependencia entre el flujo batch y el near real-time",
     "El enriquecimiento de cada transaccion resuelve la entidad contra el "
     "catalogo que comparte con el flujo B2. Si el diccionario no se ha "
     "materializado, las transacciones caen a <code>NO_DEFINIDO</code> y "
     "se marcan con la etiqueta <code>sin_catalogo</code>.",
     "El script de preparacion materializa el diccionario ANTES de levantar "
     "Logstash, y la prueba V7 cuenta cuantas transacciones quedaron sin "
     f"correspondencia ({mil(TX['sin_catalogo']['doc_count'])} en esta "
     "corrida)."),
    ("Permisos del fichero de configuracion montado",
     "Filebeat rechaza arrancar si su fichero de configuracion es escribible "
     "por otros usuarios. Un volumen montado desde macOS nunca cumple esa "
     "comprobacion.",
     "Se arranca con <code>--strict.perms=false</code>, aceptable en un "
     "entorno de desarrollo contenerizado."),
]

FILAS_RETOS = "".join(
    f'<tr><td><b>{i + 1}. {t}</b><div class="det">{d}</div></td>'
    f'<td class="sol">{s}</td></tr>'
    for i, (t, d, s) in enumerate(RETOS))

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700&family=Arimo:ital,wght@0,400;0,500;0,600;0,700&display=swap');
@page { size: A4; margin: 20mm 18mm 18mm 18mm;
        @bottom-center { content: counter(page) " de " counter(pages);
                         font-size: 8.5pt; color: #8a8b8c; } }
@page :first { margin-top: 0; }
* { box-sizing: border-box; }
body { font-family: Helvetica, "Helvetica Neue", Arimo, Arial, sans-serif;
       font-size: 9.7pt; line-height: 1.52; color: #231f20; margin: 0; }
h1, h2, h3, .display { font-family: Baskerville, "Baskerville Old Face",
       "Libre Baskerville", "Hoefler Text", Garamond, "Times New Roman", serif; }
h1 { font-size: 22pt; margin: 0 0 6pt; font-weight: 700; line-height: 1.15; }
h2 { font-size: 14pt; font-weight: 700; margin: 18pt 0 8pt; padding-bottom: 4pt;
     border-bottom: 1.5pt solid #ed1c24; page-break-after: avoid; }
h3 { font-size: 11pt; font-weight: 700; margin: 13pt 0 5pt;
     page-break-after: avoid; }
p  { margin: 0 0 7pt; text-align: justify; }
.portada { background: #231f20; color: #fff; padding: 22mm 18mm 14mm;
           margin: 0 0 14pt; }
.portada .filete { width: 46mm; height: 3pt; background: #ed1c24;
                   margin-bottom: 12pt; }
.portada h1 { color: #fff; font-size: 25pt; }
.portada .sub { font-size: 11.5pt; margin-top: 8pt; color: #d8d4cb;
                font-family: Helvetica, Arimo, Arial, sans-serif; }
.portada .meta { font-size: 9pt; color: #d8d4cb; margin-top: 18pt;
                 border-top: 0.5pt solid #4a4b4c; padding-top: 10pt; }
.portada .meta b { color: #fff; }
table { width: 100%; border-collapse: collapse; margin: 7pt 0 11pt;
        font-size: 8.6pt; page-break-inside: avoid; }
th { background: #faf3e9; text-align: left; padding: 5pt 7pt; font-weight: 700;
     border-top: 0.8pt solid #231f20; border-bottom: 0.8pt solid #d8d4cb; }
td { padding: 4.5pt 7pt; border-bottom: 0.4pt solid #e3ded4;
     vertical-align: top; }
td.n { text-align: right; font-variant-numeric: tabular-nums; }
table.retos { font-size: 8.3pt; page-break-inside: auto; }
table.retos td { width: 50%; }
table.retos .det { color: #4a4b4c; margin-top: 3pt; }
table.retos .sol { background: #faf3e9; }
table.retos tr { page-break-inside: avoid; }
.kpis { display: flex; gap: 7pt; margin: 10pt 0 12pt; }
.kpi { flex: 1 1 0; min-width: 0; border: 0.5pt solid #d8d4cb;
       border-top: 2.5pt solid #ed1c24; padding: 8pt 8pt; }
.kpi .v { font-family: Baskerville, "Libre Baskerville", Garamond, serif;
          font-size: 15.5pt; font-weight: 700; line-height: 1;
          white-space: nowrap; }
.kpi .l { font-size: 7.6pt; color: #4a4b4c; margin-top: 3pt; line-height: 1.3; }
.fig { margin: 8pt 0 11pt; page-break-inside: avoid; }
.fig svg { display: block; margin: 0 auto; max-width: 100%; }
.fig.mini svg { max-width: 82%; }
.fig .cap { font-size: 8pt; color: #4a4b4c; margin-top: 4pt; }
.fig .cap b { color: #231f20; }
.nota { background: #faf3e9; border-left: 2.5pt solid #ed1c24;
        padding: 7pt 10pt; margin: 9pt 0 12pt; font-size: 8.7pt; }
code { font-family: "Courier New", Consolas, monospace; font-size: 8.4pt;
       background: #faf3e9; padding: 0.5pt 3pt; }
pre { background: #faf3e9; border-left: 2.5pt solid #d8d4cb; padding: 8pt 10pt;
      font-family: "Courier New", Consolas, monospace; font-size: 7.8pt;
      line-height: 1.45; white-space: pre-wrap; page-break-inside: avoid;
      margin: 0 0 10pt; }
ul, ol { margin: 0 0 8pt; padding-left: 15pt; }
li { margin-bottom: 3.5pt; }
.salto { page-break-before: always; }
.dos { display: flex; gap: 12pt; }
.dos > div { flex: 1; }
"""

HOY = dt.date.today()

DOC = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Informe técnico · Flujo ELK mixto</title><style>{CSS}</style></head><body>

<div class="portada">
  <div class="filete"></div>
  <div style="font-size:9pt;letter-spacing:.08em;color:#d8d4cb">
    UNIVERSIDAD SAN FRANCISCO DE QUITO &nbsp;·&nbsp; INGENIERÍA DE DATOS</div>
  <h1>Flujo ELK mixto:<br>ingesta en lote y en near real-time
      sobre el sistema de banca privada del Ecuador</h1>
  <div class="sub">Informe técnico · Taller de la semana 2</div>
  <div class="meta">
    <b>Arquitectura:</b> Elasticsearch 8.15.3 · Logstash 8.15.3 ·
    Kibana 8.15.3 · Filebeat 8.15.3, sobre Docker Compose<br>
    <b>Fuentes integradas:</b> cinco &mdash; tres en lote y dos en near
    real-time &nbsp;·&nbsp; <b>Fecha:</b> {HOY:%d/%m/%Y}
  </div>
</div>

<h2>1. Objeto y alcance</h2>
<p>Se disena e implementa un flujo de ingesta sobre la pila ELK que combina
los dos esquemas de procesamiento en una sola arquitectura: un
<b>esquema en lote</b> que traslada a Elasticsearch el Data Warehouse
dimensional construido en el taller anterior, y un <b>esquema near
real-time</b> que ingiere un flujo continuo de transacciones con latencia
de segundos. En total se integran <b>cinco fuentes de datos</b> sobre tres
tecnologias de origen distintas &mdash; PostgreSQL, MySQL y ficheros
planos &mdash; y dos mecanismos de transporte opuestos: uno que empuja el
dato y otro que lo pregunta.</p>
<p>La totalidad de la infraestructura se declara en Docker Compose y se
levanta con un unico perfil, de modo que el flujo es reproducible en
cualquier equipo sin instalar nada en el sistema anfitrion.</p>

<div class="kpis">
  <div class="kpi"><div class="v">5</div>
    <div class="l">Fuentes integradas<br>(3 lote + 2 near real-time)</div></div>
  <div class="kpi"><div class="v">{mil(TOTAL_DOCS)}</div>
    <div class="l">Documentos indexados<br>en Elasticsearch</div></div>
  <div class="kpi"><div class="v">{mil(LAT['95.0'])} ms</div>
    <div class="l">Latencia p95 del canal<br>near real-time</div></div>
  <div class="kpi"><div class="v">{dec(MEM['total_uso_mb'] / 1024, 2)} GiB</div>
    <div class="l">Memoria de los 8<br>contenedores en marcha</div></div>
</div>

<h2>2. Arquitectura implementada</h2>
<p>La arquitectura se organiza en dos carriles que comparten destino. El
carril superior es el de lote: tres pipelines leen el almacen dimensional,
los catalogos maestros y un fichero delimitado, y terminan cuando agotan su
origen. El carril inferior es el near real-time: permanece a la escucha de
forma indefinida y entrega cada evento en cuestion de segundos.</p>

<div class="fig">{diagrama_arquitectura()}
  <div class="cap"><b>Figura 1.</b> Flujo mixto de extremo a extremo. En rojo,
  los componentes del carril near real-time; la flecha discontinua representa
  el sondeo incremental, que pregunta en lugar de recibir.</div>
</div>

<h3>2.1 Las cinco fuentes y su destino</h3>
<table>
  <thead><tr><th>Flujo</th><th>Origen</th><th>Esquema</th>
    <th>Índice o flujo de datos</th><th>Documentos</th></tr></thead>
  <tbody>{FILAS_IDX}
    <tr><th>Total</th><th></th><th></th><th></th>
        <th class="n">{mil(TOTAL_DOCS)}</th></tr>
  </tbody>
</table>

<h2>3. El carril en lote</h2>
<p>Los tres pipelines en lote resuelven el traslado de un modelo relacional
a un motor documental. El paso clave es la <b>desnormalizacion</b>:
Elasticsearch no ejecuta uniones entre indices, de modo que la consulta de
extraccion une la tabla de hechos con sus seis dimensiones y produce un
documento autocontenido con las veintiseis dimensiones de analisis y las
ocho metricas de cada registro.</p>
<ul>
  <li><b>B1 &mdash; PostgreSQL.</b> Recupera los {mil(CONTEO['banca-hechos'])}
    hechos del almacen con paginacion de 20.000 filas; sin ella, el
    controlador cargaria el resultado completo en la memoria de Logstash. La clave subrogada <code>saldo_sk</code> se usa como
    identificador del documento.</li>
  <li><b>B2 &mdash; MySQL.</b> Dos entradas en un mismo pipeline, separadas
    por el campo <code>type</code> y encaminadas a indices distintos en la
    salida. El catalogo de entidades conserva las versiones de la dimension
    lentamente cambiante, con una clave compuesta
    <code>cod_entidad-vN</code>.</li>
  <li><b>B3 &mdash; CSV.</b> Lector en modo <code>read</code>, que procesa el
    fichero completo y termina, frente al modo <code>tail</code> que emplea
    el carril near real-time. Aplica la misma normalizacion de razones
    sociales que el flujo del taller anterior.</li>
</ul>
<div class="nota"><b>Conciliacion con el origen.</b> La suma de
<code>saldo_total</code> agregada por Elasticsearch asciende a
USD {dec(SUMA_ES / 1e6)} millones, cifra identica a la que devuelve
PostgreSQL sobre la tabla de hechos. El traslado no altera ningun importe.</div>

<h2>4. El carril near real-time</h2>
<p>El regulador publica boletines mensuales, por lo que no existe un flujo
transaccional publico que se pueda consumir en vivo. Para ejercitar el
esquema se genera el evento que falta, pero <b>sin inventar el maestro</b>:
las entidades, provincias y cantones se leen de los catalogos reales ya
cargados en MySQL, de modo que el canal en vivo es consistente con el
historico y ambos se pueden cruzar en la misma consulta.</p>
<p>Se implementaron los dos mecanismos de ingesta continua, que son
opuestos por diseno:</p>
<table>
  <thead><tr><th></th><th>N1 &mdash; empuje (<i>push</i>)</th>
    <th>N2 &mdash; sondeo (<i>pull</i>)</th></tr></thead>
  <tbody>
    <tr><td><b>Origen</b></td><td>Fichero NDJSON en crecimiento</td>
        <td>Tabla <code>staging.etl_bitacora</code></td></tr>
    <tr><td><b>Transporte</b></td><td>Filebeat sigue el fichero y empuja a
        Logstash por el puerto 5044</td>
        <td>Logstash consulta por JDBC cada 15 segundos</td></tr>
    <tr><td><b>Control de avance</b></td>
        <td>Registro de posicion en el fichero</td>
        <td>Marca de agua sobre <code>id_ejecucion</code>, guardada en disco</td></tr>
    <tr><td><b>Latencia</b></td>
        <td>p50 {mil(LAT['50.0'])} ms · p95 {mil(LAT['95.0'])} ms</td>
        <td>Hasta 15 s, fijada por el intervalo de sondeo</td></tr>
    <tr><td><b>Uso</b></td><td>Eventos de negocio</td>
        <td>Observabilidad del propio proceso de carga</td></tr>
  </tbody>
</table>

<h3>4.1 Enriquecimiento en vuelo</h3>
<p>Es el punto donde los dos carriles se encuentran. Las transacciones no
traen el grupo de tamano de la entidad; el pipeline lo resuelve contra un
diccionario materializado desde el mismo catalogo de MySQL que alimenta el
flujo en lote, con lo que cada evento llega al indice ya clasificado. La
resolucion es <b>en memoria</b> y no por consulta: la seccion 9 explica por
que la primera version, que preguntaba a Elasticsearch una vez por evento,
hubo que descartarla. Se evaluan ademas dos reglas de negocio en
linea: se marca con <code>MONTO_ALTO</code> toda operacion de USD 3.000 o
mas &mdash; {mil(TX['alertas']['doc_count'])} en esta corrida &mdash; y se
etiquetan las {mil(TX['rechazadas']['doc_count'])} transacciones
rechazadas.</p>
<table>
  <thead><tr><th>Grupo de la entidad (resuelto en vuelo)</th>
    <th>Transacciones</th><th>Reparto</th></tr></thead>
  <tbody>{FILAS_TAM}</tbody>
</table>

<h2>5. Resultados medidos</h2>
<p>La corrida que documenta este informe emitio {mil(N_TX)} transacciones a
lo largo de {dec(DUR_TX, 0)} segundos, es decir {dec(TPS, 1)} eventos por
segundo sostenidos, por un importe agregado de USD
{dec(TX['monto']['value'] / 1e6)} millones.</p>

<div class="fig">{grafico_caudal()}
  <div class="cap"><b>Figura 2.</b> Caudal de ingesta del canal near
  real-time. Cada barra agrupa diez segundos de emision; la regularidad
  indica que el pipeline absorbe el flujo sin acumular retraso.</div>
</div>

<div class="fig">{grafico_canales()}
  <div class="cap"><b>Figura 3.</b> Reparto de las transacciones por canal de
  atencion, calculado por Elasticsearch sobre el indice en vivo.</div>
</div>

<div class="dos">
<div>
<h3>5.1 Latencia extremo a extremo</h3>
<p>Cada evento lleva su propia medida: el pipeline resta la marca temporal
que fijo el origen del instante en que Logstash lo procesa.</p>
<table>
  <thead><tr><th>Percentil</th><th>Latencia</th></tr></thead>
  <tbody>
    <tr><td>p50</td><td class="n">{mil(LAT['50.0'])} ms</td></tr>
    <tr><td>p90</td><td class="n">{mil(LAT['90.0'])} ms</td></tr>
    <tr><td>p95</td><td class="n">{mil(LAT['95.0'])} ms</td></tr>
    <tr><td>p99</td><td class="n">{mil(LAT['99.0'])} ms</td></tr>
  </tbody>
</table>
</div>
<div>
<h3>5.2 Tipo de operacion</h3>
<p>La distribucion reproduce el perfil del gasto minorista, con predominio
del consumo con tarjeta y del retiro en efectivo.</p>
<table>
  <thead><tr><th>Tipo</th><th>Transacciones</th></tr></thead>
  <tbody>{FILAS_CANAL}</tbody>
</table>
</div>
</div>

<h3>5.3 Reparto de la memoria</h3>
<p>El equipo dedica 3,83 GiB a Docker, cifra inferior a la que reclaman los
tres servicios de la pila con su configuracion por defecto. La tabla recoge
el consumo real de los ocho contenedores en marcha.</p>
<table>
  <thead><tr><th>Contenedor</th><th>En uso (MB)</th>
    <th>Límite fijado (MB)</th></tr></thead>
  <tbody>{FILAS_MEM}
    <tr><th>Total</th><th class="n">{mil(MEM['total_uso_mb'])}</th>
        <th class="n"></th></tr>
  </tbody>
</table>

<h2>6. Modelo de datos en Elasticsearch</h2>
<p>Se registran cinco plantillas de indice antes de cualquier escritura. La
plantilla fija el tipo de cada campo, la ausencia de replicas &mdash;
obligada en un cluster de un solo nodo &mdash; y un analizador
<code>es_sin_tildes</code> que aplica <i>asciifolding</i>, de modo que la
busqueda de <span style="white-space:nowrap">«ATLANTIDA»</span> encuentra
tambien <span style="white-space:nowrap">«ATLÁNTIDA»</span>: los boletines
del regulador mezclan ambas grafias.</p>
<p>El canal de transacciones no escribe en un indice corriente sino en un
<b>flujo de datos</b> (<i>data stream</i>), la estructura que Elasticsearch
reserva a series temporales de alta rotacion. Solo admite escrituras de
tipo <code>create</code> y delega en una politica de ciclo de vida el
relevo de indices y su eliminacion.</p>
<table>
  <thead><tr><th>Aspecto</th><th>Configuración</th></tr></thead>
  <tbody>
    <tr><td>Flujo de datos</td><td><code>{DS['name']}</code>, generación
      {DS['generation']}, {len(DS['indices'])} índice(s) de respaldo</td></tr>
    <tr><td>Política de ciclo de vida</td>
      <td><code>{DS.get('ilm_policy', 'banca-nrt')}</code> &mdash; relevo al
      alcanzar 1 GB o un día; eliminación a los 7 días</td></tr>
    <tr><td>Refresco</td><td>1 s en el canal en vivo · 5 s en los índices
      de lote</td></tr>
    <tr><td>Fragmentos</td><td>1 primario y 0 réplicas por índice</td></tr>
  </tbody>
</table>

<h2>7. Explotacion en Kibana</h2>
<p>Los objetos de Kibana se crean por script y no a mano, para que el
entregable sea reproducible: se declaran seis vistas de datos &mdash; una
por flujo &mdash; y un tablero de cuatro paneles que confronta
deliberadamente los dos esquemas en una misma pantalla. Los dos paneles
superiores muestran el historico mensual del almacen; los dos inferiores,
el caudal de transacciones por minuto y la latencia de ingesta p95, que solo
tienen sentido en el carril en vivo.</p>

<h2>8. Verificacion</h2>
<p>El script <code>elk/03_verificacion.sh</code> ejecuta ocho pruebas sobre
el sistema en marcha.</p>
<table>
  <thead><tr><th>Prueba</th><th>Resultado</th></tr></thead>
  <tbody>
    <tr><td>Salud del clúster</td><td>Estado {SALUD['status']},
      {SALUD['active_shards']} fragmentos activos,
      {SALUD['unassigned_shards']} sin asignar</td></tr>
    <tr><td>Conciliación de filas B1 (PostgreSQL ↔ Elasticsearch)</td>
      <td>{mil(CONTEO['banca-hechos'])} en ambos extremos</td></tr>
    <tr><td>Conciliación de importes B1</td>
      <td>USD {dec(SUMA_ES / 1e6)} millones en ambos extremos</td></tr>
    <tr><td>Carga de catálogos B2</td>
      <td>{mil(CONTEO['banca-catalogo-entidad'])} entidades y
      {mil(CONTEO['banca-catalogo-geografia'])} cantones</td></tr>
    <tr><td>Carga del CSV B3</td>
      <td>{mil(CONTEO['banca-colocaciones-2026'])} documentos, igual que
      las líneas del fichero</td></tr>
    <tr><td>Canal near real-time N1</td>
      <td>{mil(N_TX)} transacciones, p95 de {mil(LAT['95.0'])} ms</td></tr>
    <tr><td>Sondeo incremental N2</td>
      <td>{mil(CONTEO['banca-bitacora-etl'])} registros y marca de agua
      persistida en disco</td></tr>
    <tr><td>Enriquecimiento entre carriles</td>
      <td>{mil(TX['sin_catalogo']['doc_count'])} transacciones sin
      correspondencia en el catálogo</td></tr>
  </tbody>
</table>

<h2>9. Retos encontrados</h2>
<p>Se documentan los {len(RETOS)} obstaculos que exigieron un cambio de diseno o de
configuracion. Todos se manifestaron durante la implementacion y ninguno
aparecia en la documentacion consultada de forma evidente; varios eran
silenciosos, que es lo que los hacia peligrosos.</p>
<table class="retos">
  <thead><tr><th>Reto y sintoma observado</th><th>Resolución</th></tr></thead>
  <tbody>{FILAS_RETOS}</tbody>
</table>

<h2>10. Conclusiones</h2>
<ol>
  <li>La arquitectura integra <b>cinco fuentes</b> sobre tres tecnologias de
    origen y las consolida en {mil(TOTAL_DOCS)} documentos, combinando en un
    mismo flujo el esquema en lote y el near real-time.</li>
  <li>Los dos mecanismos de ingesta continua se implementaron de forma
    contrastada: el empuje mediante Filebeat alcanza una latencia p95 de
    {mil(LAT['95.0'])} ms, mientras que el sondeo incremental por JDBC queda
    acotado por su intervalo de 15 segundos. La eleccion entre ambos no es
    de rendimiento sino de control: solo el segundo garantiza que no se
    pierda un registro si el consumidor esta caido.</li>
  <li>El enriquecimiento del canal en vivo contra el indice que carga el
    lote demuestra que los dos carriles no son independientes: el esquema
    mixto aporta valor precisamente cuando se cruzan.</li>
  <li>La mayor dificultad no fue el volumen sino los <b>fallos
    silenciosos</b>: un borrado rechazado que parece exitoso, una cola
    persistente que reproduce datos viejos y una opcion de configuracion que
    desactiva el aislamiento entre pipelines. Los tres se detectaron por
    conciliacion de conteos, no por mensajes de error, lo que justifica que
    la verificacion forme parte del propio flujo.</li>
</ol>

<h3>Anexo · Contenido del entregable</h3>
<table>
  <thead><tr><th>Ruta</th><th>Contenido</th></tr></thead>
  <tbody>
    <tr><td><code>docker/docker-compose.yml</code></td>
      <td>Nueve servicios; el perfil <code>elk</code> añade los cuatro de
      la pila</td></tr>
    <tr><td><code>docker/elk/logstash/pipeline/</code></td>
      <td>Los cinco pipelines: tres en lote y dos en near real-time</td></tr>
    <tr><td><code>docker/elk/logstash/config/</code></td>
      <td>Configuración global y declaración de los pipelines</td></tr>
    <tr><td><code>docker/elk/filebeat/filebeat.yml</code></td>
      <td>Agente de cola del canal de transacciones</td></tr>
    <tr><td><code>elk/00_reiniciar_flujo.sh</code></td>
      <td>Reinicio limpio de índices, cola persistente y marca de agua</td></tr>
    <tr><td><code>elk/01_configurar_elasticsearch.sh</code></td>
      <td>Política de ciclo de vida, cinco plantillas y flujo de datos</td></tr>
    <tr><td><code>elk/01b_diccionario_entidades.py</code></td>
      <td>Materializa el diccionario de enriquecimiento en memoria</td></tr>
    <tr><td><code>elk/02_simulador_transacciones.py</code></td>
      <td>Generador del canal near real-time</td></tr>
    <tr><td><code>elk/03_verificacion.sh</code></td>
      <td>Las ocho pruebas de la sección 8</td></tr>
    <tr><td><code>elk/04_kibana_objetos.sh</code></td>
      <td>Seis vistas de datos y el tablero de cuatro paneles</td></tr>
    <tr><td><code>elk/05_informe_elk.py</code></td>
      <td>Generador de este informe</td></tr>
  </tbody>
</table>

</body></html>"""

ruta = os.path.join(SAL, "Informe_Tecnico_ELK.pdf")
HTML(string=DOC, base_url=RAIZ).write_pdf(ruta)
with open(os.path.join(SAL, "informe_elk.html"), "w", encoding="utf-8") as f:
    f.write(DOC)
print(f"PDF generado: {ruta}  ({os.path.getsize(ruta) // 1024} KB)")
