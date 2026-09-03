#!/usr/bin/env bash
# =====================================================================
# PASO 0 - Reinicio limpio del flujo ELK
# ---------------------------------------------------------------------
# Deja Elasticsearch y Logstash como recien instalados. Es necesario
# cada vez que se cambia un pipeline, porque Logstash guarda estado en
# tres sitios distintos y ninguno se limpia solo:
#
#   1. los indices y el flujo de datos en Elasticsearch;
#   2. la COLA PERSISTENTE en el volumen lsdata, que conserva los
#      eventos ya aceptados y los reproduce al arrancar de nuevo;
#   3. el REGISTRO de Filebeat en el volumen fbdata, que recuerda hasta
#      que byte leyo cada fichero. Si Logstash estuvo caido, Filebeat
#      conserva los eventos sin confirmar y los reenvia al reconectar;
#   4. la marca de agua .bitacora_last_run del sondeo incremental;
#   5. el propio fichero NDJSON del volumen nrtlogs. Si sobrevive, al
#      vaciar el registro Filebeat lo lee entero otra vez y reinyecta
#      transacciones antiguas, con latencias de horas que falsean la
#      medida del canal.
#
# El contenedor debe ELIMINARSE, no solo detenerse: Docker se niega a
# borrar un volumen que un contenedor -aunque este parado- todavia usa,
# y el fallo es silencioso.
#
# Uso:  bash elk/00_reiniciar_flujo.sh
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")/../docker"

echo "== 1/4  Eliminando los contenedores de Logstash y Filebeat"
docker compose --profile elk rm -sf logstash filebeat > /dev/null 2>&1
echo "        contenedores eliminados"

echo "== 2/4  Purgando el estado persistente"
for v in lsdata fbdata; do
  if docker volume rm "taller-etl-dw_$v" > /dev/null 2>&1; then
    echo "        volumen $v purgado"
  else
    echo "        AVISO: el volumen $v sigue en uso"
  fi
done
# El fichero de transacciones se vacia, no se borra: Filebeat vigila esa
# ruta y conviene que exista desde el principio.
if docker exec etl_runtime sh -c ": > /logs/transacciones.ndjson" 2>/dev/null; then
  echo "        fichero NDJSON vaciado"
else
  echo "        AVISO: no se pudo vaciar /logs/transacciones.ndjson"
fi

echo "== 3/4  Borrando indices y flujo de datos en Elasticsearch"
# El flujo de datos se borra por su propia API: sus indices de respaldo
# (.ds-*) estan protegidos y no se pueden borrar uno a uno.
docker exec elk_elasticsearch curl -sS -XDELETE \
  "http://localhost:9200/_data_stream/banca-transacciones" > /dev/null 2>&1

# Los indices se enumeran y se borran POR NOMBRE. Un DELETE con comodin
# ("banca-*") se rechaza siempre: el ajuste action.destructive_requires_name
# vale "true" por defecto en Elasticsearch 8. El error llega en el cuerpo
# de la respuesta con codigo 400, asi que si se descarta la salida el
# borrado parece haber funcionado y los datos viejos siguen ahi.
INDICES=$(docker exec elk_elasticsearch curl -sS \
  "http://localhost:9200/_cat/indices/banca-*?h=index" | tr -d '\r' | paste -sd, -)
if [ -n "$INDICES" ]; then
  RESP=$(docker exec elk_elasticsearch curl -sS -XDELETE "http://localhost:9200/$INDICES")
  if echo "$RESP" | grep -q '"acknowledged":true'; then
    echo "        borrados: $INDICES"
  else
    echo "        ERROR al borrar: $RESP"; exit 1
  fi
else
  echo "        no habia indices que borrar"
fi

echo "== 4/4  Recreando plantillas y levantando Logstash"
bash ../elk/01_configurar_elasticsearch.sh > /dev/null 2>&1
docker compose --profile elk up -d logstash filebeat > /dev/null 2>&1
echo "        Logstash y Filebeat arrancando"

echo
echo "Comprobando que los CINCO pipelines arrancaron..."
# No basta con que Logstash arranque: si un pipeline tiene la
# configuracion mal, Logstash sigue en pie con los demas y el fallo pasa
# inadvertido. Se consulta la API de nodo, que solo lista los que corren.
ESPERADOS="b1-pg-hechos b2-mysql-catalogos b3-csv-colocaciones n1-beats-transacciones n2-jdbc-bitacora"
for i in $(seq 1 60); do
  ACTIVOS=$(docker exec elk_logstash curl -sS http://localhost:9600/_node/pipelines 2>/dev/null |
            python3 -c "import sys,json;print(' '.join(sorted(json.load(sys.stdin)['pipelines'])))" 2>/dev/null || echo "")
  if [ -n "$ACTIVOS" ]; then
    FALTAN=""
    for p in $ESPERADOS; do
      case " $ACTIVOS " in *" $p "*) ;; *) FALTAN="$FALTAN $p";; esac
    done
    if [ -z "$FALTAN" ]; then
      echo "        los 5 pipelines estan activos"
      break
    fi
    # Los pipelines batch terminan solos al agotar su origen; se espera un
    # poco antes de declararlo un fallo.
    if [ "$i" -gt 12 ]; then
      echo "        ERROR: no arrancaron:$FALTAN"
      echo "        causa probable en el registro:"
      docker logs elk_logstash --since 5m 2>&1 |
        grep -oE "Unknown setting '[^']+' for [a-z_]+|Expected one of .{0,60}" |
        sort -u | head -3 | sed 's/^/          /'
      exit 1
    fi
  fi
  sleep 5
done
echo
echo "REINICIO COMPLETADO. Los tres flujos batch se cargan solos."
echo "Para el canal near real-time ejecute el simulador:"
echo "  docker exec etl_runtime python elk/02_simulador_transacciones.py --duracion 120 --tps 20"
