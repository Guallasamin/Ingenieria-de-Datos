#!/usr/bin/env bash
# =====================================================================
# PASO 4 - Vistas de datos y tablero en Kibana
# ---------------------------------------------------------------------
# Crea, por API, las cinco vistas de datos (una por flujo) y un tablero
# que contrasta el esquema BATCH con el NEAR REAL-TIME.
#
# Se hace por script y no a mano para que el entregable sea reproducible:
# quien clone el repositorio obtiene exactamente los mismos objetos.
#
# Uso:  bash elk/04_kibana_objetos.sh
# =====================================================================
set -uo pipefail

KB() { docker exec -i elk_kibana curl -sS -H 'kbn-xsrf: true' -H 'Content-Type: application/json' "$@"; }

echo "== Esperando a que Kibana este disponible (puede tardar ~90 s)..."
for i in $(seq 1 60); do
  ESTADO=$(docker exec elk_kibana curl -sS http://localhost:5601/api/status 2>/dev/null |
           python3 -c "import sys,json;print(json.load(sys.stdin)['status']['overall']['level'])" 2>/dev/null || echo "")
  [ "$ESTADO" = "available" ] && { echo "   Kibana disponible."; break; }
  [ "$i" = 60 ] && { echo "   ERROR: Kibana no llego a estar disponible."; exit 1; }
  sleep 5
done

# ---------------------------------------------------------------------
# Vistas de datos: una por flujo
# ---------------------------------------------------------------------
# Formato:  id | patron de indice | campo temporal | nombre visible
VISTAS=(
  "dv-hechos|banca-hechos|@timestamp|B1 · Hechos del DW (batch)"
  "dv-catalogo-entidad|banca-catalogo-entidad||B2 · Catálogo de entidades (batch)"
  "dv-catalogo-geografia|banca-catalogo-geografia||B2 · Catálogo geográfico (batch)"
  "dv-colocaciones|banca-colocaciones-2026|@timestamp|B3 · Colocaciones CSV (batch)"
  "dv-transacciones|banca-transacciones|@timestamp|N1 · Transacciones (near real-time)"
  "dv-bitacora|banca-bitacora-etl|@timestamp|N2 · Bitácora del ETL (near real-time)"
)

echo
echo "== Creando vistas de datos"
for v in "${VISTAS[@]}"; do
  IFS='|' read -r ID PATRON CAMPO NOMBRE <<< "$v"
  if [ -n "$CAMPO" ]; then
    CUERPO="{\"data_view\":{\"id\":\"$ID\",\"title\":\"$PATRON\",\"name\":\"$NOMBRE\",\"timeFieldName\":\"$CAMPO\"},\"override\":true}"
  else
    CUERPO="{\"data_view\":{\"id\":\"$ID\",\"title\":\"$PATRON\",\"name\":\"$NOMBRE\"},\"override\":true}"
  fi
  R=$(KB -XPOST http://localhost:5601/api/data_views/data_view -d "$CUERPO")
  if echo "$R" | grep -q "\"id\":\"$ID\""; then
    printf "   OK    %-22s -> %s\n" "$ID" "$PATRON"
  else
    printf "   FALLO %-22s %s\n" "$ID" "$(echo "$R" | head -c 160)"
  fi
done

# ---------------------------------------------------------------------
# Tablero: cuatro paneles que confrontan los dos esquemas
# ---------------------------------------------------------------------
# Cada objeto se crea con la API de objetos guardados y NO con la de
# importacion: al importar, Kibana encadena las migraciones historicas del
# tipo "lens" y una de ellas falla sobre un objeto escrito a mano
# ("Cannot read properties of undefined (reading 'layers')"). La creacion
# directa almacena el objeto ya en la version vigente.
echo
echo "== Creando las visualizaciones y el tablero"
python3 - <<'PY'
import json
import subprocess

def crear(tipo, oid, atributos, referencias):
    cuerpo = json.dumps({"attributes": atributos, "references": referencias})
    r = subprocess.run(
        ["docker", "exec", "-i", "elk_kibana", "curl", "-sS",
         "-H", "kbn-xsrf: true", "-H", "Content-Type: application/json",
         "-XPOST",
         f"http://localhost:5601/api/saved_objects/{tipo}/{oid}?overwrite=true",
         "-d", "@-"],
        input=cuerpo, capture_output=True, text=True)
    ok = f'"id":"{oid}"' in r.stdout
    print(f"   {'OK   ' if ok else 'FALLO'} {tipo:<10} {oid}")
    if not ok:
        print("         " + r.stdout[:200])
    return ok


def xy(tipo, y):
    return {"legend": {"isVisible": True, "position": "right"},
            "valueLabels": "hide", "preferredSeriesType": tipo,
            "layers": [{"layerId": "c1", "accessors": [y], "position": "top",
                        "seriesType": tipo, "showGridlines": False,
                        "layerType": "data", "xAccessor": "x"}]}


def lens(titulo, vista, columnas, visualizacion):
    return ({"title": titulo, "visualizationType": "lnsXY",
             "state": {
                 "datasourceStates": {"formBased": {"layers": {"c1": {
                     "columns": columnas, "columnOrder": ["x", "y"],
                     "incompleteColumns": {}}}}},
                 "filters": [], "query": {"language": "kuery", "query": ""},
                 "visualization": visualizacion}},
            [{"type": "index-pattern", "id": vista,
              "name": "indexpattern-datasource-layer-c1"}])


def fecha(intervalo):
    return {"label": "@timestamp", "dataType": "date",
            "operationType": "date_histogram", "sourceField": "@timestamp",
            "isBucketed": True, "scale": "interval",
            "params": {"interval": intervalo, "includeEmptyRows": True}}


def metrica(op, campo, etiqueta, extra=None):
    return {"label": etiqueta, "dataType": "number", "operationType": op,
            "sourceField": campo, "isBucketed": False, "scale": "ratio",
            "params": extra if extra else {"emptyAsNull": True}}


PANELES = [
    ("viz-saldos-mes", "B1 - Saldo del sistema por mes (lote)", "dv-hechos",
     {"x": fecha("1M"), "y": metrica("sum", "saldo_total", "Saldo total")},
     xy("line", "y")),
    ("viz-morosidad", "B1 - Cartera improductiva por familia (lote)",
     "dv-hechos",
     {"x": {"label": "Familia", "dataType": "string", "operationType": "terms",
            "sourceField": "familia", "isBucketed": True, "scale": "ordinal",
            "params": {"size": 10,
                       "orderBy": {"type": "column", "columnId": "y"},
                       "orderDirection": "desc"}},
      "y": metrica("sum", "saldo_improductivo", "Cartera improductiva")},
     xy("bar_horizontal", "y")),
    ("viz-tx-caudal", "N1 - Transacciones por minuto (near real-time)",
     "dv-transacciones",
     {"x": fecha("1m"),
      "y": {"label": "Transacciones", "dataType": "number",
            "operationType": "count", "sourceField": "___records___",
            "isBucketed": False, "scale": "ratio",
            "params": {"emptyAsNull": False}}},
     xy("bar_stacked", "y")),
    ("viz-tx-latencia", "N1 - Latencia de ingesta p95 (near real-time)",
     "dv-transacciones",
     {"x": fecha("1m"),
      "y": metrica("percentile", "latencia_ingesta_ms",
                   "p95 de latencia (ms)", {"percentile": 95})},
     xy("line", "y")),
]

ok = True
for oid, titulo, vista, columnas, visualizacion in PANELES:
    atributos, referencias = lens(titulo, vista, columnas, visualizacion)
    ok &= crear("lens", oid, atributos, referencias)

# --- el tablero agrupa los cuatro paneles en una reticula 2x2 ---------
paneles, refs = [], []
for i, (oid, *_) in enumerate(PANELES):
    pid = f"p{i + 1}"
    paneles.append({"version": "8.15.3", "type": "lens",
                    "gridData": {"x": (i % 2) * 24, "y": (i // 2) * 15,
                                 "w": 24, "h": 15, "i": pid},
                    "panelIndex": pid, "embeddableConfig": {"enhancements": {}},
                    "panelRefName": f"panel_{pid}"})
    refs.append({"name": f"panel_{pid}", "type": "lens", "id": oid})

ok &= crear("dashboard", "tablero-banca-elk", {
    "title": "Banca Ecuador - flujo ELK mixto",
    "description": "Lote (Data Warehouse) y near real-time (transacciones) "
                   "en un mismo tablero.",
    "panelsJSON": json.dumps(paneles),
    "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
    "timeRestore": False, "version": 1,
    "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(
        {"query": {"language": "kuery", "query": ""}, "filter": []})},
}, refs)

raise SystemExit(0 if ok else 1)
PY

echo
echo "PASO 4 COMPLETADO"
echo "   Kibana:  http://localhost:5601"
echo "   Tablero: Analytics > Dashboard > 'Banca Ecuador · flujo ELK mixto'"
