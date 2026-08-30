# Flujo ETL multifuente y Data Warehouse — Banca privada del Ecuador

**Taller Individual - Ingeniería de Datos**

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

## Accesos

| Servicio | URL / conexión | Credenciales |
|---|---|---|
| PostgreSQL (staging + DW) | `localhost:5432` · BD `banca_ec` | `etl_user` / `etl_pass_2026` |
| MySQL (catálogos) | `localhost:3306` · BD `catalogos_sb` | `etl_user` / `etl_pass_2026` |
| Adminer (consola web) | http://localhost:8080 | mismas credenciales |
| Metabase (OLAP, opcional) | http://localhost:3000 · `docker compose --profile bi up -d` | — |

---

## Estructura del proyecto

```
.
├── data/                              FUENTE 3 — 18 libros Excel originales
│   └── 2024|2025|2026 / Cartera|Depositos
├── docker/
│   ├── docker-compose.yml             5 servicios
│   ├── postgres/init/
│   │   ├── 01_esquemas_y_staging.sql  esquemas staging y dw
│   │   ├── 02_ddl_dw_estrella.sql     modelo estrella (6 dim + 1 fact)
│   │   └── 03_vistas_olap.sql         cubo + 4 vistas de KPI
│   └── mysql/init/01_catalogos.sql    catálogos maestros
├── etl/
│   ├── 01_extraccion_fuentes.py       prepara y puebla las 4 fuentes
│   ├── 02_carga_dw.py                 ETL de carga del DW (espejo del flujo KNIME)
│   ├── 03_validacion.sql              8 pruebas de validación
│   ├── 04_informe.py                  genera el informe técnico en PDF
│   └── 05_informe_web.py              genera la versión web del informe
├── fuentes/csv/colocaciones_2026.csv  FUENTE 4
├── knime/
│   ├── ETL_Banca_Ecuador.knwf         ENTREGABLE — flujo KNIME (122 nodos)
│   ├── ETL_Banca_Ecuador/             el flujo sin comprimir
│   └── GUIA_FLUJO_KNIME.md            documentación del flujo
├── informe/
│   ├── Informe_Tecnico_ETL_DW.pdf   ENTREGABLE — informe técnico (5 páginas)
│   └── artefacto.html                 misma información, versión web
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

