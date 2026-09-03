#!/usr/bin/env bash
# =====================================================================
# PASO 1 - Preparar Elasticsearch antes de la ingesta
# ---------------------------------------------------------------------
# Declara la politica de ciclo de vida (ILM), las plantillas de indice y
# el flujo de datos del canal near real-time.
#
# El orden importa: si Logstash escribe ANTES de que exista la plantilla,
# Elasticsearch infiere el mapeo dinamicamente y los importes quedan como
# texto, con lo que ninguna agregacion (sum, avg) funciona.
#
# Uso:  bash elk/01_configurar_elasticsearch.sh
# =====================================================================
set -euo pipefail

ES="docker exec -i elk_elasticsearch curl -sS -H Content-Type:application/json"

echo "== Esperando a Elasticsearch..."
for i in $(seq 1 60); do
  if docker exec elk_elasticsearch curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
    echo "   Elasticsearch responde."; break
  fi
  [ "$i" = 60 ] && { echo "   ERROR: no responde"; exit 1; }
  sleep 3
done

# ---------------------------------------------------------------------
# 1. Politica ILM para el canal near real-time
# ---------------------------------------------------------------------
# Las transacciones son datos de alta rotacion: se acumulan rapido y
# pierden valor operativo en dias. Rollover por tamanio/edad y borrado.
echo "== ILM: politica banca-nrt"
$ES -XPUT http://localhost:9200/_ilm/policy/banca-nrt -d '{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": { "max_primary_shard_size": "1gb", "max_age": "1d" }
        }
      },
      "delete": {
        "min_age": "7d",
        "actions": { "delete": {} }
      }
    }
  }
}' > /dev/null && echo "   OK"

# ---------------------------------------------------------------------
# 2. Ajustes comunes
# ---------------------------------------------------------------------
# Un solo nodo => 0 replicas. Con la replica por defecto (1) el cluster
# queda permanentemente en amarillo porque no hay donde colocarla.
COMUNES='"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "5s"'

# Analizador que ignora tildes: permite buscar "ATLANTIDA" y encontrar
# "ATLÁNTIDA". Los boletines del regulador mezclan ambas grafias.
ANALIZADOR='"analysis": {
    "analyzer": {
      "es_sin_tildes": {
        "tokenizer": "standard",
        "filter": ["lowercase", "asciifolding"]
      }
    }
  }'

# ---------------------------------------------------------------------
# 3. Plantilla: hechos del Data Warehouse (BATCH B1)
# ---------------------------------------------------------------------
echo "== Plantilla: banca-hechos"
$ES -XPUT http://localhost:9200/_index_template/banca-hechos -d "{
  \"index_patterns\": [\"banca-hechos\"],
  \"priority\": 200,
  \"template\": {
    \"settings\": { $COMUNES, $ANALIZADOR },
    \"mappings\": {
      \"properties\": {
        \"@timestamp\":        { \"type\": \"date\" },
        \"saldo_sk\":          { \"type\": \"long\" },
        \"anio\":              { \"type\": \"short\" },
        \"semestre\":          { \"type\": \"byte\" },
        \"trimestre\":         { \"type\": \"byte\" },
        \"mes\":               { \"type\": \"byte\" },
        \"nombre_mes\":        { \"type\": \"keyword\" },
        \"anio_mes\":          { \"type\": \"keyword\" },
        \"etiqueta_trim\":     { \"type\": \"keyword\" },
        \"cod_entidad\":       { \"type\": \"keyword\" },
        \"entidad\":           { \"type\": \"text\",
                                 \"analyzer\": \"es_sin_tildes\",
                                 \"fields\": { \"raw\": { \"type\": \"keyword\" } } },
        \"estado_entidad\":    { \"type\": \"keyword\" },
        \"grupo_tamanio\":     { \"type\": \"keyword\" },
        \"perfil_negocio\":    { \"type\": \"keyword\" },
        \"region\":            { \"type\": \"keyword\" },
        \"provincia\":         { \"type\": \"keyword\" },
        \"canton\":            { \"type\": \"keyword\" },
        \"nivel_bancarizacion\": { \"type\": \"keyword\" },
        \"nombre_producto\":   { \"type\": \"keyword\" },
        \"familia\":           { \"type\": \"keyword\" },
        \"subfamilia\":        { \"type\": \"keyword\" },
        \"cuenta_contable\":   { \"type\": \"keyword\" },
        \"nombre_operacion\":  { \"type\": \"keyword\" },
        \"naturaleza\":        { \"type\": \"keyword\" },
        \"cod_fuente\":        { \"type\": \"keyword\" },
        \"tipo_tecnologia\":   { \"type\": \"keyword\" },
        \"saldo_total\":        { \"type\": \"double\" },
        \"saldo_por_vencer\":   { \"type\": \"double\" },
        \"saldo_no_devenga\":   { \"type\": \"double\" },
        \"saldo_vencido\":      { \"type\": \"double\" },
        \"saldo_improductivo\": { \"type\": \"double\" },
        \"numero_cuentas\":     { \"type\": \"long\" },
        \"numero_clientes\":    { \"type\": \"long\" },
        \"indice_morosidad\":   { \"type\": \"half_float\" }
      }
    }
  }
}" > /dev/null && echo "   OK"

# ---------------------------------------------------------------------
# 4. Plantilla: catalogos maestros (BATCH B2)
# ---------------------------------------------------------------------
echo "== Plantilla: banca-catalogo-*"
$ES -XPUT http://localhost:9200/_index_template/banca-catalogo -d "{
  \"index_patterns\": [\"banca-catalogo-*\"],
  \"priority\": 200,
  \"template\": {
    \"settings\": { $COMUNES, $ANALIZADOR },
    \"mappings\": {
      \"properties\": {
        \"cod_entidad\":      { \"type\": \"keyword\" },
        \"cod_geografia\":    { \"type\": \"keyword\" },
        \"nombre_entidad\":   { \"type\": \"text\", \"analyzer\": \"es_sin_tildes\",
                                \"fields\": { \"raw\": { \"type\": \"keyword\" } } },
        \"nombre_comercial\": { \"type\": \"keyword\" },
        \"grupo_tamanio\":    { \"type\": \"keyword\" },
        \"perfil_negocio\":   { \"type\": \"keyword\" },
        \"estado_entidad\":   { \"type\": \"keyword\" },
        \"vigente\":          { \"type\": \"boolean\" },
        \"version\":          { \"type\": \"integer\" },
        \"region\":           { \"type\": \"keyword\" },
        \"provincia\":        { \"type\": \"keyword\" },
        \"canton\":           { \"type\": \"keyword\" },
        \"type\":             { \"type\": \"keyword\" }
      }
    }
  }
}" > /dev/null && echo "   OK"

# ---------------------------------------------------------------------
# 5. Plantilla: colocaciones desde CSV (BATCH B3)
# ---------------------------------------------------------------------
echo "== Plantilla: banca-colocaciones-*"
$ES -XPUT http://localhost:9200/_index_template/banca-colocaciones -d "{
  \"index_patterns\": [\"banca-colocaciones-*\"],
  \"priority\": 200,
  \"template\": {
    \"settings\": { $COMUNES, $ANALIZADOR },
    \"mappings\": {
      \"properties\": {
        \"@timestamp\":           { \"type\": \"date\" },
        \"fecha_corte\":          { \"type\": \"date\", \"format\": \"yyyy-MM-dd\" },
        \"entidad\":              { \"type\": \"keyword\" },
        \"provincia\":            { \"type\": \"keyword\" },
        \"canton\":               { \"type\": \"keyword\" },
        \"segmento\":             { \"type\": \"keyword\" },
        \"archivo_origen\":       { \"type\": \"keyword\" },
        \"por_vencer\":           { \"type\": \"double\" },
        \"no_devenga_intereses\": { \"type\": \"double\" },
        \"vencida\":              { \"type\": \"double\" },
        \"total_saldo\":          { \"type\": \"double\" }
      }
    }
  }
}" > /dev/null && echo "   OK"

# ---------------------------------------------------------------------
# 6. Plantilla + flujo de datos: transacciones (NRT N1)
# ---------------------------------------------------------------------
# Un data stream solo admite escrituras de tipo "create" y gestiona el
# rollover por si mismo mediante la politica ILM declarada arriba.
echo "== Plantilla y flujo de datos: banca-transacciones"
$ES -XPUT http://localhost:9200/_index_template/banca-transacciones -d "{
  \"index_patterns\": [\"banca-transacciones\"],
  \"priority\": 200,
  \"data_stream\": {},
  \"template\": {
    \"settings\": {
      \"number_of_shards\": 1, \"number_of_replicas\": 0,
      \"refresh_interval\": \"1s\",
      \"index.lifecycle.name\": \"banca-nrt\"
    },
    \"mappings\": {
      \"properties\": {
        \"@timestamp\":          { \"type\": \"date\" },
        \"id_tx\":               { \"type\": \"keyword\" },
        \"ts_origen\":           { \"type\": \"date\" },
        \"cod_entidad\":         { \"type\": \"keyword\" },
        \"entidad\":             { \"type\": \"keyword\" },
        \"grupo_tamanio\":       { \"type\": \"keyword\" },
        \"perfil_negocio\":      { \"type\": \"keyword\" },
        \"canal\":               { \"type\": \"keyword\" },
        \"tipo_transaccion\":    { \"type\": \"keyword\" },
        \"provincia\":           { \"type\": \"keyword\" },
        \"canton\":              { \"type\": \"keyword\" },
        \"id_cliente\":          { \"type\": \"keyword\" },
        \"moneda\":              { \"type\": \"keyword\" },
        \"estado\":              { \"type\": \"keyword\" },
        \"alerta\":              { \"type\": \"keyword\" },
        \"monto\":               { \"type\": \"double\" },
        \"latencia_ingesta_ms\": { \"type\": \"integer\" },
        \"tags\":                { \"type\": \"keyword\" }
      }
    }
  }
}" > /dev/null && echo "   OK"

# El flujo de datos se crea explicitamente para que exista aunque aun no
# haya llegado ninguna transaccion.
docker exec elk_elasticsearch curl -sS -XPUT \
  http://localhost:9200/_data_stream/banca-transacciones > /dev/null 2>&1 || true

# ---------------------------------------------------------------------
# 7. Plantilla: bitacora del ETL (NRT N2)
# ---------------------------------------------------------------------
echo "== Plantilla: banca-bitacora-etl"
$ES -XPUT http://localhost:9200/_index_template/banca-bitacora -d "{
  \"index_patterns\": [\"banca-bitacora-*\"],
  \"priority\": 200,
  \"template\": {
    \"settings\": { $COMUNES },
    \"mappings\": {
      \"properties\": {
        \"@timestamp\":       { \"type\": \"date\" },
        \"id_ejecucion\":     { \"type\": \"long\" },
        \"proceso\":          { \"type\": \"keyword\" },
        \"fuente\":           { \"type\": \"keyword\" },
        \"objeto_destino\":   { \"type\": \"keyword\" },
        \"estado\":           { \"type\": \"keyword\" },
        \"salud\":            { \"type\": \"keyword\" },
        \"mensaje\":          { \"type\": \"text\" },
        \"filas_leidas\":     { \"type\": \"long\" },
        \"filas_escritas\":   { \"type\": \"long\" },
        \"filas_rechazadas\": { \"type\": \"long\" },
        \"duracion_seg\":     { \"type\": \"float\" }
      }
    }
  }
}" > /dev/null && echo "   OK"

# ---------------------------------------------------------------------
# 8. Diccionario de enriquecimiento del canal en vivo
# ---------------------------------------------------------------------
# Debe existir ANTES de que arranque Logstash: el filtro translate lo lee
# al iniciar el pipeline.
echo "== Diccionario de entidades para el canal near real-time"
if docker exec etl_runtime python elk/01b_diccionario_entidades.py 2>&1 |
   sed 's/^/   /'; then :; else
  echo "   AVISO: no se pudo generar; el canal marcara NO_DEFINIDO"
fi

echo
echo "== Plantillas registradas:"
docker exec elk_elasticsearch curl -sS \
  "http://localhost:9200/_cat/templates/banca-*?h=name,index_patterns&v"
echo
echo "PASO 1 COMPLETADO - Elasticsearch listo para recibir los 5 flujos."
