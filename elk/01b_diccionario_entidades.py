#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PASO 1b - Materializa el diccionario de enriquecimiento del canal en vivo
=============================================================================
El canal near real-time necesita anadir a cada transaccion el grupo de
tamanio y el perfil de negocio de la entidad, datos que solo estan en la
dimension. La primera version consultaba Elasticsearch con el filtro
"elasticsearch" UNA VEZ POR EVENTO; cada consulta es un viaje de ida y
vuelta por HTTP y el pipeline no lograba sostener 20 eventos por segundo:
la cola crecia sin limite y la latencia p99 llegaba a 313 segundos.

Una dimension de 26 filas no se consulta por red: se carga en memoria. Este
script la materializa como diccionario YAML y el filtro "translate" lo lee
al arrancar, con recarga periodica. El coste por evento pasa de una consulta
de red a una busqueda en un mapa.

Ejecucion:  docker exec etl_runtime python elk/01b_diccionario_entidades.py
"""
import os

import pandas as pd
from sqlalchemy import create_engine

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "docker", "elk", "logstash",
                       "diccionario", "entidades.yml")

MY = "mysql+pymysql://{u}:{p}@{h}:{P}/{d}?charset=utf8mb4".format(
    u=os.getenv("MY_USER", "etl_user"), p=os.getenv("MY_PASS", "etl_pass_2026"),
    h=os.getenv("MY_HOST", "mysql"), P=os.getenv("MY_PORT", "3306"),
    d=os.getenv("MY_DB", "catalogos_sb"))


def main():
    eng = create_engine(MY)
    # Solo la version vigente de cada entidad: el canal en vivo describe
    # operaciones de hoy, no historia.
    d = pd.read_sql("""
        SELECT cod_entidad, grupo_tamanio, perfil_negocio
        FROM cat_entidad_financiera
        WHERE es_vigente = 1
        ORDER BY cod_entidad""", eng)
    eng.dispose()

    if d.empty:
        raise SystemExit("ERROR: no hay entidades vigentes en MySQL. "
                         "Ejecute antes etl/01_extraccion_fuentes.py")

    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with open(DESTINO, "w", encoding="utf-8") as f:
        f.write("# Diccionario de enriquecimiento del canal near real-time.\n")
        f.write("# GENERADO por elk/01b_diccionario_entidades.py - no editar.\n")
        f.write("# Formato:  <cod_entidad>: \"<grupo_tamanio>|<perfil_negocio>\"\n")
        for _, r in d.iterrows():
            f.write(f'"{r.cod_entidad}": "{r.grupo_tamanio}|{r.perfil_negocio}"\n')

    print(f"Diccionario escrito: {DESTINO}")
    print(f"   {len(d)} entidades vigentes")


if __name__ == "__main__":
    main()
