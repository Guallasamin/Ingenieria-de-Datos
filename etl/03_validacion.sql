-- =====================================================================
-- PASO 3 - VALIDACIÓN Y CONCILIACIÓN DEL DATA WAREHOUSE
-- Ejecutar:  docker exec -i etl_postgres psql -U etl_user -d banca_ec \
--              -f /proyecto/etl/03_validacion.sql
-- =====================================================================
\echo '=== V1. Conteo de filas por objeto del modelo estrella ==='
SELECT 'dim_tiempo'          AS objeto, COUNT(*) FROM dw.dim_tiempo
UNION ALL SELECT 'dim_entidad',         COUNT(*) FROM dw.dim_entidad
UNION ALL SELECT 'dim_geografia',       COUNT(*) FROM dw.dim_geografia
UNION ALL SELECT 'dim_producto',        COUNT(*) FROM dw.dim_producto
UNION ALL SELECT 'dim_tipo_operacion',  COUNT(*) FROM dw.dim_tipo_operacion
UNION ALL SELECT 'dim_fuente_datos',    COUNT(*) FROM dw.dim_fuente_datos
UNION ALL SELECT 'FACT_saldos',         COUNT(*) FROM dw.fact_saldos_financieros;

\echo ''
\echo '=== V2. Integridad referencial: huérfanos en la tabla de hechos (debe ser 0) ==='
SELECT
  COUNT(*) FILTER (WHERE t.tiempo_sk        IS NULL) AS sin_tiempo,
  COUNT(*) FILTER (WHERE e.entidad_sk       IS NULL) AS sin_entidad,
  COUNT(*) FILTER (WHERE g.geografia_sk     IS NULL) AS sin_geografia,
  COUNT(*) FILTER (WHERE p.producto_sk      IS NULL) AS sin_producto,
  COUNT(*) FILTER (WHERE o.tipo_operacion_sk IS NULL) AS sin_operacion,
  COUNT(*) FILTER (WHERE f.fuente_sk        IS NULL) AS sin_fuente
FROM dw.fact_saldos_financieros h
LEFT JOIN dw.dim_tiempo         t ON t.tiempo_sk        = h.tiempo_sk
LEFT JOIN dw.dim_entidad        e ON e.entidad_sk       = h.entidad_sk
LEFT JOIN dw.dim_geografia      g ON g.geografia_sk     = h.geografia_sk
LEFT JOIN dw.dim_producto       p ON p.producto_sk      = h.producto_sk
LEFT JOIN dw.dim_tipo_operacion o ON o.tipo_operacion_sk= h.tipo_operacion_sk
LEFT JOIN dw.dim_fuente_datos   f ON f.fuente_sk        = h.fuente_sk;

\echo ''
\echo '=== V3. Trazabilidad: aporte de cada una de las 4 fuentes al DW ==='
SELECT f.cod_fuente, f.tipo_tecnologia,
       CASE WHEN f.cod_fuente='F2_MYSQL' THEN 'DIMENSIONES'
            ELSE 'TABLA DE HECHOS' END                       AS alimenta,
       COALESCE(x.filas,
         (SELECT COUNT(*) FROM dw.dim_entidad)
       + (SELECT COUNT(*) FROM dw.dim_geografia)
       + (SELECT COUNT(*) FROM dw.dim_producto)
       + (SELECT COUNT(*) FROM dw.dim_tipo_operacion)
       + (SELECT COUNT(*) FROM dw.dim_fuente_datos))         AS filas_aportadas,
       COALESCE(TO_CHAR(x.saldo/1e6,'FM999G999G990D00'),'-') AS saldo_millones_usd
FROM dw.dim_fuente_datos f
LEFT JOIN (SELECT fuente_sk, COUNT(*) filas, SUM(saldo_total) saldo
           FROM dw.fact_saldos_financieros GROUP BY 1) x ON x.fuente_sk=f.fuente_sk
ORDER BY f.cod_fuente;

\echo ''
\echo '=== V4. Conciliación con el origen (staging vs. DW) ==='
SELECT 'staging.captaciones' AS origen,
       COUNT(*) AS filas, ROUND(SUM(saldo)/1e6,2) AS saldo_mm
FROM staging.captaciones_banca_privada
UNION ALL
SELECT 'dw.fact (captaciones)', COUNT(*), ROUND(SUM(h.saldo_total)/1e6,2)
FROM dw.fact_saldos_financieros h
JOIN dw.dim_tipo_operacion o ON o.tipo_operacion_sk=h.tipo_operacion_sk
WHERE o.nombre_operacion='CAPTACION';

\echo ''
\echo '=== V5. SCD Tipo 2: historial de entidades con más de una versión ==='
SELECT cod_entidad, version, nombre_entidad, estado_entidad,
       fecha_inicio_vig, fecha_fin_vig, es_vigente
FROM dw.dim_entidad
WHERE cod_entidad IN (SELECT cod_entidad FROM dw.dim_entidad
                      GROUP BY cod_entidad HAVING COUNT(*)>1)
ORDER BY cod_entidad, version;

\echo ''
\echo '=== V6. Jerarquía geográfica Región > Provincia > Cantón ==='
SELECT region, COUNT(DISTINCT provincia) AS provincias, COUNT(*) AS cantones
FROM dw.dim_geografia GROUP BY region ORDER BY cantones DESC;

\echo ''
\echo '=== V7. Cobertura temporal ==='
SELECT MIN(anio_mes) AS desde, MAX(anio_mes) AS hasta,
       COUNT(*) AS cortes_mensuales, COUNT(DISTINCT anio) AS anios
FROM dw.dim_tiempo;

\echo ''
\echo '=== V8. Regla de negocio: TOTAL = POR VENCER + NO DEVENGA + VENCIDA (debe ser 0) ==='
SELECT COUNT(*) AS filas_descuadradas
FROM dw.fact_saldos_financieros
WHERE saldo_por_vencer IS NOT NULL
  AND ABS(saldo_total - (saldo_por_vencer + saldo_no_devenga + saldo_vencido)) > 0.05;

\echo ''
\echo '=== V9. Conciliación entre implementaciones: ETL Python vs. flujo KNIME ==='
SELECT objeto, python, knime,
       CASE WHEN python = knime THEN 'OK' ELSE 'DIFIERE' END AS cuadre
FROM (
  SELECT 'dim_tiempo' AS objeto,
         (SELECT COUNT(*) FROM dw.dim_tiempo)              AS python,
         (SELECT COUNT(*) FROM dw_knime.dim_tiempo)        AS knime
  UNION ALL SELECT 'dim_entidad',
         (SELECT COUNT(*) FROM dw.dim_entidad),        (SELECT COUNT(*) FROM dw_knime.dim_entidad)
  UNION ALL SELECT 'dim_geografia',
         (SELECT COUNT(*) FROM dw.dim_geografia),      (SELECT COUNT(*) FROM dw_knime.dim_geografia)
  UNION ALL SELECT 'dim_producto',
         (SELECT COUNT(*) FROM dw.dim_producto),       (SELECT COUNT(*) FROM dw_knime.dim_producto)
  UNION ALL SELECT 'dim_tipo_operacion',
         (SELECT COUNT(*) FROM dw.dim_tipo_operacion), (SELECT COUNT(*) FROM dw_knime.dim_tipo_operacion)
  UNION ALL SELECT 'dim_fuente_datos',
         (SELECT COUNT(*) FROM dw.dim_fuente_datos),   (SELECT COUNT(*) FROM dw_knime.dim_fuente_datos)
  UNION ALL SELECT 'fact_saldos_financieros',
         (SELECT COUNT(*) FROM dw.fact_saldos_financieros),
         (SELECT COUNT(*) FROM dw_knime.fact_saldos_financieros)
) x ORDER BY 1;

\echo ''
\echo '=== V10. Los importes tambien deben coincidir ==='
WITH py AS (
    SELECT o.naturaleza, SUM(h.saldo_total) AS saldo
    FROM dw.fact_saldos_financieros h
    JOIN dw.dim_tipo_operacion o USING (tipo_operacion_sk) GROUP BY 1),
     kn AS (
    SELECT o.naturaleza, SUM(h.saldo_total) AS saldo
    FROM dw_knime.fact_saldos_financieros h
    JOIN dw_knime.dim_tipo_operacion o USING (tipo_operacion_sk) GROUP BY 1)
SELECT py.naturaleza,
       ROUND(py.saldo/1e6, 2) AS python_millones,
       ROUND(kn.saldo/1e6, 2) AS knime_millones,
       CASE WHEN ROUND(py.saldo,2) = ROUND(kn.saldo,2) THEN 'OK' ELSE 'DIFIERE' END AS cuadre
FROM py JOIN kn USING (naturaleza) ORDER BY 1;
