-- =====================================================================
-- CAPA OLAP  |  Vistas del cubo sobre el modelo estrella
-- Estas vistas son el "cubo" que consume la herramienta de BI
-- (Metabase / Power BI / Excel) sin escribir joins a mano.
-- =====================================================================
SET search_path TO dw, public;

-- ---------------------------------------------------------------------
-- VISTA BASE DEL CUBO: estrella completamente desnormalizada.
-- Todas las jerarquías disponibles para drill-down / roll-up / slice&dice.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW dw.v_cubo_banca AS
SELECT
    -- ===== Eje TIEMPO (jerarquía Año > Semestre > Trimestre > Mes) =====
    t.fecha, t.anio, t.semestre, t.trimestre, t.mes,
    t.nombre_mes, t.anio_mes, t.etiqueta_trim,
    -- ===== Eje ENTIDAD (Grupo tamaño > Perfil > Entidad) =====
    e.cod_entidad, e.nombre_comercial AS entidad,
    e.estado_entidad, e.grupo_tamanio, e.perfil_negocio, e.cobertura_geo,
    -- ===== Eje GEOGRAFÍA (Región > Provincia > Cantón) =====
    g.region, g.provincia, g.canton, g.nivel_bancarizacion,
    -- ===== Eje PRODUCTO (Familia > Subfamilia > Producto) =====
    p.familia, p.subfamilia, p.nombre_producto, p.cuenta_contable, p.es_a_la_vista,
    -- ===== Eje OPERACIÓN =====
    o.nombre_operacion, o.naturaleza,
    -- ===== Eje FUENTE (linaje) =====
    f.tipo_tecnologia AS fuente_tecnologia, f.nombre_fuente,
    -- ===== MÉTRICAS =====
    h.saldo_total, h.saldo_por_vencer, h.saldo_no_devenga, h.saldo_vencido,
    h.saldo_improductivo, h.numero_cuentas, h.numero_clientes,
    h.saldo_promedio_cliente
FROM dw.fact_saldos_financieros h
JOIN dw.dim_tiempo         t ON t.tiempo_sk        = h.tiempo_sk
JOIN dw.dim_entidad        e ON e.entidad_sk       = h.entidad_sk
JOIN dw.dim_geografia      g ON g.geografia_sk     = h.geografia_sk
JOIN dw.dim_producto       p ON p.producto_sk      = h.producto_sk
JOIN dw.dim_tipo_operacion o ON o.tipo_operacion_sk= h.tipo_operacion_sk
JOIN dw.dim_fuente_datos   f ON f.fuente_sk        = h.fuente_sk;

COMMENT ON VIEW dw.v_cubo_banca IS 'Cubo desnormalizado: 6 ejes de análisis y 8 métricas.';

-- ---------------------------------------------------------------------
-- KPI 1: Índice de morosidad por entidad y mes
--        morosidad = cartera improductiva / cartera bruta
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW dw.v_kpi_morosidad AS
SELECT
    anio, anio_mes, entidad, grupo_tamanio, subfamilia AS segmento_credito,
    SUM(saldo_total)        AS cartera_bruta,
    SUM(saldo_improductivo) AS cartera_improductiva,
    ROUND(100.0 * SUM(saldo_improductivo) / NULLIF(SUM(saldo_total),0), 2) AS pct_morosidad
FROM dw.v_cubo_banca
WHERE naturaleza = 'ACTIVO'
GROUP BY anio, anio_mes, entidad, grupo_tamanio, subfamilia;

-- ---------------------------------------------------------------------
-- KPI 2: Intermediación financiera (colocaciones / captaciones)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW dw.v_kpi_intermediacion AS
SELECT
    anio, anio_mes, entidad, region, provincia,
    SUM(saldo_total) FILTER (WHERE naturaleza = 'ACTIVO') AS colocaciones,
    SUM(saldo_total) FILTER (WHERE naturaleza = 'PASIVO') AS captaciones,
    ROUND(
      SUM(saldo_total) FILTER (WHERE naturaleza = 'ACTIVO')
      / NULLIF(SUM(saldo_total) FILTER (WHERE naturaleza = 'PASIVO'),0), 4
    ) AS ratio_intermediacion
FROM dw.v_cubo_banca
GROUP BY anio, anio_mes, entidad, region, provincia;

-- ---------------------------------------------------------------------
-- KPI 3: Concentración territorial y participación de mercado
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW dw.v_kpi_participacion AS
WITH base AS (
    SELECT anio_mes, naturaleza, region, provincia, entidad,
           SUM(saldo_total) AS saldo
    FROM dw.v_cubo_banca
    GROUP BY anio_mes, naturaleza, region, provincia, entidad
)
SELECT b.*,
       ROUND(100.0 * saldo / NULLIF(SUM(saldo) OVER (PARTITION BY anio_mes, naturaleza),0), 3)
         AS pct_mercado_nacional,
       RANK() OVER (PARTITION BY anio_mes, naturaleza ORDER BY saldo DESC) AS ranking
FROM base b;

-- ---------------------------------------------------------------------
-- KPI 4: Evolución mensual del sistema con variación intermensual
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW dw.v_kpi_evolucion AS
WITH m AS (
    SELECT anio_mes, naturaleza, SUM(saldo_total) AS saldo
    FROM dw.v_cubo_banca GROUP BY anio_mes, naturaleza
)
SELECT anio_mes, naturaleza, saldo,
       LAG(saldo) OVER (PARTITION BY naturaleza ORDER BY anio_mes) AS saldo_mes_anterior,
       ROUND(100.0 * (saldo - LAG(saldo) OVER (PARTITION BY naturaleza ORDER BY anio_mes))
             / NULLIF(LAG(saldo) OVER (PARTITION BY naturaleza ORDER BY anio_mes),0), 2) AS var_pct_mensual
FROM m;
