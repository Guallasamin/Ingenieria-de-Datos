# Banca privada del Ecuador — ETL dimensional y flujo ELK

**Talleres de Ingeniería de Datos** · dos entregas sobre el mismo conjunto de datos.

| Semana | Entrega | Resumen |
|---|---|---|
| **1** | ETL multifuente + Data Warehouse | 4 fuentes heterogéneas → modelo estrella (6 dimensiones + 1 tabla de hechos), en KNIME y en Python |
| **2** | Flujo ELK mixto | 5 fuentes → Elasticsearch, combinando **lote** y **near real-time** |

---

## Semana 1 — ETL y Data Warehouse

Flujo ETL que integra **4 fuentes de datos heterogéneas** y las consolida en un
**Data Warehouse en modelo estrella** con 6 dimensiones y 1 tabla de hechos.

| | |
|---|---|
| **Origen** | Superintendencia de Bancos del Ecuador — Colocaciones y Captaciones de banca privada |
| **Periodo** | enero 2024 – mayo 2026 (29 cortes mensuales) |
| **Volumen** | 176.990 registros de hechos · 26 entidades · 126 cantones · 19 productos |
| **DW** | PostgreSQL 16 — `dw` (ETL Python) y `dw_knime` (flujo KNIME) |

---

## Puesta en marcha (3 comandos)

```bash
cd docker && docker compose up -d                             # postgres, mysql, adminer, runtime
docker exec etl_runtime python etl/01_extraccion_fuentes.py   # prepara las 4 fuentes
docker exec etl_runtime python etl/02_carga_dw.py             # puebla el modelo estrella
```

Luego, en KNIME: **File ▸ Import KNIME Workflow…** →
[knime/ETL_Banca_Ecuador.knwf](knime/ETL_Banca_Ecuador.knwf) → *Execute all*.
El flujo carga el mismo modelo estrella en el esquema `dw_knime`.

Ambos caminos producen el **mismo** Data Warehouse, cifra por cifra:

| Objeto | ETL Python (`dw`) | Flujo KNIME (`dw_knime`) |
|---|---:|---:|
| dim_tiempo | 29 | 29 |
| dim_entidad | 26 | 26 |
| dim_geografia | 126 | 126 |
| dim_producto | 19 | 19 |
| dim_tipo_operacion | 2 | 2 |
| dim_fuente_datos | 4 | 4 |
| **fact_saldos_financieros** | **176.990** | **176.990** |

Validar el resultado:

```bash
docker exec -i etl_postgres psql -U etl_user -d banca_ec -f - < etl/03_validacion.sql
```

---

## Fuentes

| # | Tecnología | Contenido | Filas | Alimenta |
|---|---|---|---|---|
| 1 | **PostgreSQL** | `staging.captaciones_banca_privada` | 122.217 | tabla de hechos |
| 2 | **MySQL** | `catalogos_sb` — 5 catálogos maestros | 177 | dimensiones |
| 3 | **Excel XLSX** | 10 libros de cartera 2024–2025 (hoja `BASE …`) | 45.341 | tabla de hechos |
| 4 | **CSV** | `fuentes/csv/colocaciones_2026.csv` (delimitador `;`) | 9.432 | tabla de hechos |

## Modelo estrella

```
                         dim_tiempo (29)
                                |
  dim_entidad (26, SCD2) -------+------- dim_geografia (126)
                                |
                    fact_saldos_financieros
                         176.990 filas
                                |
  dim_producto (19) -----------+-------- dim_tipo_operacion (2)
                                |
                       dim_fuente_datos (4)
```

**Jerarquías OLAP:**
- Tiempo: Año → Semestre → Trimestre → Mes
- Entidad: Grupo de tamaño → Perfil de negocio → Entidad
- Geografía: Región → Provincia → Cantón
- Producto: Familia → Subfamilia → Producto

---

---

## Semana 2 — Flujo ELK mixto (lote + near real-time)

Sobre el mismo almacén se monta un flujo de ingesta en la pila ELK que combina
los dos esquemas de procesamiento y suma **5 fuentes**.

```bash
cd docker && docker compose --profile elk up -d      # elasticsearch, logstash, kibana, filebeat
bash elk/00_reiniciar_flujo.sh                       # plantillas + los 5 pipelines (verifica que arranquen)
docker exec etl_runtime python elk/02_simulador_transacciones.py --duracion 120 --tps 20
bash elk/03_verificacion.sh                          # 8 pruebas de extremo a extremo
bash elk/04_kibana_objetos.sh                        # 6 vistas de datos + 1 tablero
```

| Flujo | Origen | Esquema | Destino en Elasticsearch |
|---|---|---|---|
| **B1** | PostgreSQL · `dw` desnormalizado | Lote | `banca-hechos` |
| **B2** | MySQL · catálogos maestros | Lote | `banca-catalogo-entidad`, `banca-catalogo-geografia` |
| **B3** | CSV · colocaciones 2026 | Lote | `banca-colocaciones-2026` |
| **N1** | NDJSON → Filebeat | **Near real-time** (empuje) | `banca-transacciones` (flujo de datos + ILM) |
| **N2** | PostgreSQL · `staging.etl_bitacora` | **Near real-time** (sondeo 15 s) | `banca-bitacora-etl` |

Los dos carriles se cruzan: cada transacción del canal en vivo se enriquece con
el grupo de tamaño de la entidad, tomado del mismo catálogo que carga el lote.

---

## Accesos

| Servicio | URL / conexión | Credenciales |
|---|---|---|
| PostgreSQL (staging + DW) | `localhost:5432` · BD `banca_ec` | `etl_user` / `etl_pass_2026` |
| MySQL (catálogos) | `localhost:3306` · BD `catalogos_sb` | `etl_user` / `etl_pass_2026` |
| Adminer (consola web) | http://localhost:8080 | mismas credenciales |
| Metabase (OLAP, opcional) | http://localhost:3000 · `docker compose --profile bi up -d` | — |
| Elasticsearch | http://localhost:9200 | sin autenticación (entorno académico) |
| Kibana | http://localhost:5601 | — |
| API de Logstash | http://localhost:9600 | — |

---

## Estructura del proyecto

```
.
├── data/                              FUENTE 3 — 18 libros Excel originales
│   └── 2024|2025|2026 / Cartera|Depositos
├── docker/
│   ├── docker-compose.yml             9 servicios (perfiles: elk, bi)
│   ├── postgres/init/
│   │   ├── 01_esquemas_y_staging.sql  esquemas staging y dw
│   │   ├── 02_ddl_dw_estrella.sql     modelo estrella (6 dim + 1 fact)
│   │   └── 03_vistas_olap.sql         cubo + 4 vistas de KPI
│   └── mysql/init/01_catalogos.sql    catálogos maestros
├── etl/
│   ├── 01_extraccion_fuentes.py       prepara y puebla las 4 fuentes
│   ├── 02_carga_dw.py                 ETL de carga del DW (espejo del flujo KNIME)
│   ├── 03_validacion.sql              10 pruebas de validación
│   ├── 04_informe.py                  genera el informe técnico en PDF
│   └── 05_informe_web.py              genera la versión web del informe
├── fuentes/csv/colocaciones_2026.csv  FUENTE 4
├── knime/
│   ├── ETL_Banca_Ecuador.knwf         ENTREGABLE — flujo KNIME (122 nodos)
│   ├── ETL_Banca_Ecuador/             el flujo sin comprimir
│   └── GUIA_FLUJO_KNIME.md            documentación del flujo
├── elk/                               SEMANA 2 — flujo ELK
│   ├── 00_reiniciar_flujo.sh          reinicio limpio y verificación de pipelines
│   ├── 01_configurar_elasticsearch.sh ILM, 5 plantillas y flujo de datos
│   ├── 01b_diccionario_entidades.py   diccionario de enriquecimiento en memoria
│   ├── 02_simulador_transacciones.py  generador del canal near real-time
│   ├── 03_verificacion.sh             8 pruebas de extremo a extremo
│   ├── 04_kibana_objetos.sh           6 vistas de datos + 1 tablero
│   └── 05_informe_elk.py              genera el informe de la semana 2
├── docker/elk/                        configuración de la pila
│   ├── logstash/pipeline/             los 5 pipelines (3 lote + 2 near real-time)
│   ├── logstash/config/               logstash.yml y pipelines.yml
│   ├── logstash/drivers/              controladores JDBC de PostgreSQL y MySQL
│   └── filebeat/filebeat.yml          agente de cola del canal en vivo
├── informe/
│   ├── Informe_Tecnico_ETL_DW.pdf   ENTREGABLE semana 1 (5 páginas)
│   ├── Informe_Tecnico_ELK.pdf     ENTREGABLE semana 2
│   └── artefacto.html                 versión web del informe de la semana 1
└── README.md
```

---

## Capa OLAP

| Vista | Qué responde |
|---|---|
| `dw.v_cubo_banca` | Estrella desnormalizada: 6 ejes y 8 métricas |
| `dw.v_kpi_morosidad` | Cartera improductiva / cartera bruta por entidad y segmento |
| `dw.v_kpi_intermediacion` | Colocaciones / captaciones por territorio |
| `dw.v_kpi_participacion` | Cuota de mercado y ranking por periodo |
| `dw.v_kpi_evolucion` | Variación intermensual del sistema |

Ejemplo de consulta con roll-up:

```sql
SELECT region, provincia,
       SUM(saldo_total) FILTER (WHERE naturaleza='ACTIVO') AS colocaciones,
       SUM(saldo_total) FILTER (WHERE naturaleza='PASIVO') AS captaciones
FROM dw.v_cubo_banca
WHERE anio_mes = '2026-05'
GROUP BY ROLLUP (region, provincia);
```

---

## Transformaciones de limpieza implementadas

| Defecto real en el origen | Tratamiento |
|---|---|
| `BP BANCO  DESARROLLO DE LOS PUEBLOS  S.A.` (espacios dobles) | colapso de espacios múltiples |
| Prefijos `BP` / `BANCO` y forma societaria `S.A.` inconsistentes | derivación de nombre comercial homogéneo |
| `ATLÁNTIDA`, `CAÑAR`, `TSÁCHILAS` | normalización NFD para las claves; tildes conservadas en la presentación |
| Cartera **no trae** la columna `REGION` | enriquecimiento por *join* contra el catálogo geográfico |
| `ZONA NO DELIMITADA` sin región | miembro `NO DEFINIDA` + bandera `es_registro_desconocido` |
| `BANCO AMIBANK S.A.` vs `…, EN LIQUIDACION` | **SCD Tipo 2**: una clave de negocio, dos versiones vigentes por rango de fechas |

---

