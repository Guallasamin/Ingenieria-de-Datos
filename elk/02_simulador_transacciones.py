#!/usr/bin/env python3
"""
PASO 2 - Simulador del flujo NEAR REAL-TIME
=============================================================================
Los boletines de la Superintendencia de Bancos son mensuales: no existe un
flujo transaccional publico que se pueda consumir en tiempo real. Este
generador produce el evento que falta, pero NO inventa el maestro: las
entidades, provincias y cantones se leen de los catalogos reales que ya
estan cargados en MySQL, de modo que el canal near real-time es
consistente con el historico del Data Warehouse y ambos se pueden cruzar.

Escribe una linea NDJSON por transaccion en logs/transacciones.ndjson.
Filebeat sigue ese fichero y lo empuja a Logstash en cuanto aparece.

Cada cierto numero de eventos registra ademas una fila en
staging.etl_bitacora, que es la fuente del segundo canal near real-time
(sondeo incremental por JDBC).

Uso:
    docker exec etl_runtime python elk/02_simulador_transacciones.py \
        --duracion 120 --tps 20
"""
import argparse
import json
import os
import random
import string
import sys
import time
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text

RAIZ = "/proyecto"
# Volumen compartido con Filebeat (ver docker-compose.yml).
SALIDA_POR_DEFECTO = os.getenv("NRT_SALIDA", "/logs/transacciones.ndjson")

MY = "mysql+pymysql://{u}:{p}@{h}:{P}/{d}?charset=utf8mb4".format(
    u=os.getenv("MY_USER", "etl_user"), p=os.getenv("MY_PASS", "etl_pass_2026"),
    h=os.getenv("MY_HOST", "mysql"), P=os.getenv("MY_PORT", "3306"),
    d=os.getenv("MY_DB", "catalogos_sb"))
PG = "postgresql+psycopg2://{u}:{p}@{h}:{P}/{d}".format(
    u=os.getenv("PG_USER", "etl_user"), p=os.getenv("PG_PASS", "etl_pass_2026"),
    h=os.getenv("PG_HOST", "postgres"), P=os.getenv("PG_PORT", "5432"),
    d=os.getenv("PG_DB", "banca_ec"))

# Canales de atencion y su peso relativo (la banca movil domina).
CANALES = [("BANCA_MOVIL", 38), ("CAJERO_AUTOMATICO", 22), ("BANCA_WEB", 16),
           ("POS_COMERCIO", 12), ("VENTANILLA", 8), ("CORRESPONSAL", 4)]

# Tipo de operacion, su peso y el rango tipico de monto en USD.
TIPOS = [("CONSUMO_TARJETA", 26, 8, 400), ("RETIRO", 24, 20, 500),
         ("TRANSFERENCIA", 20, 25, 5000), ("PAGO_SERVICIO", 18, 5, 250),
         ("DEPOSITO", 12, 30, 9000)]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def cargar_maestros():
    """Lee entidades y geografia de los catalogos reales en MySQL."""
    eng = create_engine(MY)
    ent = pd.read_sql(
        "SELECT cod_entidad, nombre_comercial, grupo_tamanio "
        "FROM cat_entidad_financiera WHERE es_vigente = 1", eng)
    geo = pd.read_sql(
        "SELECT provincia, canton FROM cat_geografia "
        "WHERE es_registro_desconocido = 0", eng)
    eng.dispose()
    if ent.empty or geo.empty:
        sys.exit("ERROR: los catalogos de MySQL estan vacios. "
                 "Ejecute antes etl/01_extraccion_fuentes.py")

    # Los bancos grandes concentran la mayor parte de las transacciones:
    # se les asigna mas peso para que la distribucion sea realista.
    peso = {"GRANDE": 60, "MEDIANO": 25, "PEQUENO": 15, "PEQUEÑO": 15}
    ent["peso"] = ent["grupo_tamanio"].map(peso).fillna(10)
    return ent, geo


def elegir(opciones, pesos):
    return random.choices(opciones, weights=pesos, k=1)[0]


def nueva_transaccion(ent, geo):
    fila_e = ent.sample(1, weights=ent["peso"]).iloc[0]
    fila_g = geo.sample(1).iloc[0]
    canal = elegir([c for c, _ in CANALES], [w for _, w in CANALES])
    tipo, _, mn, mx = elegir(TIPOS, [t[1] for t in TIPOS])

    # Distribucion sesgada a montos bajos, con cola larga hacia arriba:
    # reproduce el perfil real del gasto minorista.
    monto = round(random.triangular(mn, mx, mn + (mx - mn) * 0.18), 2)

    # 4 % de rechazos, la mayoria por fondos insuficientes.
    estado = "RECHAZADA" if random.random() < 0.04 else "APROBADA"

    return {
        "id_tx": "TX" + "".join(random.choices(string.digits, k=12)),
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "cod_entidad": fila_e["cod_entidad"],
        "entidad": fila_e["nombre_comercial"],
        "canal": canal,
        "tipo": tipo,
        "provincia": fila_g["provincia"],
        "canton": fila_g["canton"],
        "monto": monto,
        "moneda": "USD",
        "estado": estado,
        "id_cliente": "CL" + "".join(random.choices(string.digits, k=8)),
    }


def anotar_bitacora(eng, lote, enviadas, seg):
    """Alimenta el segundo canal near real-time (sondeo incremental)."""
    with eng.begin() as cx:
        cx.execute(text("""
            INSERT INTO staging.etl_bitacora
                (proceso, fuente, objeto_destino, filas_leidas, filas_escritas,
                 filas_rechazadas, estado, mensaje, inicio, fin)
            VALUES (:pr, :fu, :ob, :fl, :fe, :fr, :es, :ms, :ini, now())"""),
            {"pr": "simulador_nrt", "fu": "F5_STREAM",
             "ob": "logs/transacciones.ndjson",
             "fl": enviadas, "fe": enviadas, "fr": 0, "es": "OK",
             "ms": f"Lote {lote} del canal near real-time",
             "ini": datetime.now()})


def main():
    ap = argparse.ArgumentParser(description="Simulador del canal near real-time")
    ap.add_argument("--duracion", type=int, default=120,
                    help="segundos de emision (por defecto 120)")
    ap.add_argument("--tps", type=float, default=20,
                    help="transacciones por segundo (por defecto 20)")
    ap.add_argument("--salida", default=SALIDA_POR_DEFECTO)
    ap.add_argument("--reiniciar", action="store_true",
                    help="vacia el fichero antes de empezar")
    args = ap.parse_args()

    log("Cargando catalogos maestros desde MySQL...")
    ent, geo = cargar_maestros()
    log(f"   {len(ent)} entidades vigentes y {len(geo)} cantones.")

    eng_pg = create_engine(PG)
    os.makedirs(os.path.dirname(args.salida), exist_ok=True)
    modo = "w" if args.reiniciar else "a"

    intervalo = 1.0 / args.tps
    total = int(args.duracion * args.tps)
    log(f"Emitiendo {total} transacciones a {args.tps}/s durante "
        f"{args.duracion}s -> {args.salida}")

    enviadas, lote, t0 = 0, 0, time.time()
    with open(args.salida, modo, encoding="utf-8") as f:
        while enviadas < total:
            ciclo = time.time()
            f.write(json.dumps(nueva_transaccion(ent, geo),
                               ensure_ascii=False) + "\n")
            # Vaciado inmediato: sin esto el buffer de Python retendria las
            # lineas y Filebeat no veria nada durante varios segundos, lo
            # que arruinaria la latencia del canal.
            f.flush()
            enviadas += 1

            if enviadas % 500 == 0:
                lote += 1
                anotar_bitacora(eng_pg, lote, enviadas, time.time() - t0)
                log(f"   {enviadas}/{total} transacciones emitidas.")

            espera = intervalo - (time.time() - ciclo)
            if espera > 0:
                time.sleep(espera)

    transcurrido = time.time() - t0
    lote += 1
    anotar_bitacora(eng_pg, lote, enviadas, transcurrido)
    eng_pg.dispose()
    log(f"COMPLETADO: {enviadas} transacciones en {transcurrido:.1f}s "
        f"({enviadas / transcurrido:.1f}/s reales).")


if __name__ == "__main__":
    main()
