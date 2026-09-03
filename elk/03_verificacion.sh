#!/usr/bin/env bash
# =====================================================================
# PASO 3 - Verificacion de extremo a extremo del flujo ELK
# ---------------------------------------------------------------------
# Ocho pruebas que comprueban que los cinco flujos llegaron a
# Elasticsearch y que los datos son consistentes con el origen.
#
# Uso:  bash elk/03_verificacion.sh
# =====================================================================
set -uo pipefail

ES() { docker exec elk_elasticsearch curl -sS -H 'Content-Type: application/json' "$@"; }
PG() { docker exec etl_postgres psql -U etl_user -d banca_ec -t -A -c "$1"; }
raya() { printf '%.0s-' {1..70}; echo; }
titulo() { echo; raya; echo "$1"; raya; }

# ---------------------------------------------------------------------
titulo "V1. Salud del cluster y consumo de memoria"
ES "http://localhost:9200/_cluster/health?pretty" |
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"  estado={d['status']}  nodos={d['number_of_nodes']}  shards_activos={d['active_shards']}  no_asignados={d['unassigned_shards']}\")"
docker stats --no-stream --format "  {{.Name}}: {{.MemUsage}}" | grep -E "elk_|etl_"

# ---------------------------------------------------------------------
titulo "V2. Documentos indexados por flujo"
ES "http://localhost:9200/_cat/indices/banca-*?h=index,docs.count,store.size&s=index&v"
echo
echo "  Flujo de datos (data stream):"
ES "http://localhost:9200/_data_stream/banca-transacciones" |
  python3 -c "
import sys, json
d = json.load(sys.stdin)
for ds in d.get('data_streams', []):
    print(f\"    {ds['name']}  generacion={ds['generation']}  indices={len(ds['indices'])}  ILM={ds.get('ilm_policy','-')}\")" 2>/dev/null || echo "    (sin datos aun)"

# ---------------------------------------------------------------------
titulo "V3. BATCH B1 - Conciliacion PostgreSQL -> Elasticsearch"
PGN=$(PG "SELECT COUNT(*) FROM dw.fact_saldos_financieros")
ESN=$(ES "http://localhost:9200/banca-hechos/_count" | python3 -c "import sys,json;print(json.load(sys.stdin)['count'])")
PGS=$(PG "SELECT ROUND(SUM(saldo_total)/1e6,2) FROM dw.fact_saldos_financieros")
ESS=$(ES "http://localhost:9200/banca-hechos/_search" -d '{"size":0,"aggs":{"s":{"sum":{"field":"saldo_total"}}}}' |
      python3 -c "import sys,json;print(round(json.load(sys.stdin)['aggregations']['s']['value']/1e6,2))")
printf "  filas   PostgreSQL=%-10s Elasticsearch=%-10s %s\n" "$PGN" "$ESN" \
  "$([ "$PGN" = "$ESN" ] && echo CUADRA || echo DIFIERE)"
printf "  saldo   PostgreSQL=%-10s Elasticsearch=%-10s (millones USD)\n" "$PGS" "$ESS"

# ---------------------------------------------------------------------
titulo "V4. BATCH B2 y B3 - Catalogos (MySQL) y CSV"
for idx in banca-catalogo-entidad banca-catalogo-geografia banca-colocaciones-2026; do
  N=$(ES "http://localhost:9200/$idx/_count" | python3 -c "import sys,json;print(json.load(sys.stdin).get('count','-'))" 2>/dev/null)
  printf "  %-28s %s documentos\n" "$idx" "$N"
done
CSVN=$(( $(wc -l < /Users/jonathan/Desktop/Ingenieria\ de\ Datos/fuentes/csv/colocaciones_2026.csv) - 1 ))
echo "  origen CSV (sin cabecera):   $CSVN lineas"

# ---------------------------------------------------------------------
titulo "V5. NEAR REAL-TIME N1 - Transacciones y latencia de ingesta"
ES "http://localhost:9200/banca-transacciones/_search" -d '{
  "size": 0,
  "aggs": {
    "total":     { "value_count": { "field": "id_tx" } },
    "latencia":  { "percentiles": { "field": "latencia_ingesta_ms", "percents": [50,90,99] } },
    "por_canal": { "terms": { "field": "canal", "size": 10 } },
    "ultimo":    { "max": { "field": "@timestamp" } }
  }
}' | python3 -c "
import sys, json
d = json.load(sys.stdin)
a = d.get('aggregations')
if not a: print('  (aun no hay transacciones)'); sys.exit()
print(f\"  transacciones indexadas : {a['total']['value']:,}\".replace(',', '.'))
p = a['latencia']['values']
print(f\"  latencia p50 / p90 / p99: {p['50.0']:.0f} / {p['90.0']:.0f} / {p['99.0']:.0f} ms\")
print('  por canal:')
for b in a['por_canal']['buckets']:
    print(f\"    {b['key']:<20} {b['doc_count']:>6}\")"

# ---------------------------------------------------------------------
titulo "V6. NEAR REAL-TIME N2 - Bitacora del ETL (sondeo incremental)"
BPG=$(PG "SELECT COUNT(*) FROM staging.etl_bitacora")
BES=$(ES "http://localhost:9200/banca-bitacora-etl/_count" | python3 -c "import sys,json;print(json.load(sys.stdin).get('count','-'))" 2>/dev/null)
printf "  filas   PostgreSQL=%-8s Elasticsearch=%-8s %s\n" "$BPG" "$BES" \
  "$([ "$BPG" = "$BES" ] && echo CUADRA || echo 'pendiente del proximo sondeo (15s)')"
echo "  marca de agua guardada por Logstash:"
docker exec elk_logstash cat /usr/share/logstash/data/.bitacora_last_run 2>/dev/null | sed 's/^/    /' || echo "    (aun sin escribir)"

# ---------------------------------------------------------------------
titulo "V7. Enriquecimiento entre flujos (batch -> near real-time)"
# Las transacciones no traen el tamanio del banco: se anade en vuelo
# consultando el catalogo que cargo el flujo batch B2.
ES "http://localhost:9200/banca-transacciones/_search" -d '{
  "size": 0,
  "aggs": { "grupos": { "terms": { "field": "grupo_tamanio", "size": 5 } },
            "sin_catalogo": { "filter": { "term": { "tags": "_sin_catalogo" } } } }
}' | python3 -c "
import sys, json
a = json.load(sys.stdin).get('aggregations')
if not a: print('  (sin datos)'); sys.exit()
tot = sum(b['doc_count'] for b in a['grupos']['buckets'])
print(f\"  transacciones enriquecidas con el catalogo: {tot}\")
for b in a['grupos']['buckets']:
    print(f\"    {b['key']:<12} {b['doc_count']:>6}\")
print(f\"  sin correspondencia en el catalogo: {a['sin_catalogo']['doc_count']}\")"

# ---------------------------------------------------------------------
titulo "V8. Estado de los 5 pipelines de Logstash"
docker exec elk_logstash curl -sS "http://localhost:9600/_node/stats/pipelines" |
python3 -c "
import sys, json
d = json.load(sys.stdin)['pipelines']
print(f\"  {'pipeline':<24}{'entrada':>10}{'salida':>10}{'fallos':>9}\")
for nombre, p in sorted(d.items()):
    ev = p.get('events', {})
    fallos = sum(pl.get('failures', 0) for pl in p.get('plugins', {}).get('outputs', []))
    print(f\"  {nombre:<24}{ev.get('in',0):>10}{ev.get('out',0):>10}{fallos:>9}\")"

echo
raya
echo "VERIFICACION COMPLETADA"
raya
