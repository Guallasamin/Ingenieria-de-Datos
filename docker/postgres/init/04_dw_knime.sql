-- =====================================================================
-- Esquema espejo poblado por el FLUJO DE KNIME
-- ---------------------------------------------------------------------
-- Misma estructura que `dw`, pero cargado por ETL_Banca_Ecuador.knwf.
-- Tener los dos esquemas permite conciliar ambas implementaciones y
-- demostrar que producen exactamente el mismo Data Warehouse.
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS dw_knime AUTHORIZATION etl_user;
COMMENT ON SCHEMA dw_knime IS
    'Modelo estrella poblado por el flujo de KNIME (espejo de dw).';

-- =====================================================================
-- DATA WAREHOUSE - MODELO ESTRELLA (Kimball)
-- Esquema: dw   |  Motor: PostgreSQL 16
-- ---------------------------------------------------------------------
--                        dim_tiempo
--                             |
--   dim_entidad ----.         |         .---- dim_geografia
--                    \        |        /
--                     +--> fact_saldos_financieros <--+
--                    /        |        \
--   dim_producto ---'         |         '---- dim_fuente_datos
--                        dim_tipo_operacion
--
--  6 dimensiones + 1 tabla de hechos (el taller exige >= 5 + 1)
--  Todas las PK son claves subrogadas (surrogate keys) enteras.
-- =====================================================================

SET search_path TO dw_knime, public;

DROP TABLE IF EXISTS dw_knime.fact_saldos_financieros CASCADE;
DROP TABLE IF EXISTS dw_knime.dim_tiempo         CASCADE;
DROP TABLE IF EXISTS dw_knime.dim_entidad        CASCADE;
DROP TABLE IF EXISTS dw_knime.dim_geografia      CASCADE;
DROP TABLE IF EXISTS dw_knime.dim_producto       CASCADE;
DROP TABLE IF EXISTS dw_knime.dim_tipo_operacion CASCADE;
DROP TABLE IF EXISTS dw_knime.dim_fuente_datos   CASCADE;

-- =====================================================================
-- DIMENSIÓN 1: TIEMPO
-- Jerarquía: Año > Semestre > Trimestre > Mes
-- Tipo: estática (rol: fecha de corte contable, fin de mes)
-- =====================================================================
CREATE TABLE dw_knime.dim_tiempo (
    tiempo_sk        INTEGER      PRIMARY KEY,   -- formato AAAAMMDD
    fecha            DATE         NOT NULL UNIQUE,
    anio             SMALLINT     NOT NULL,
    semestre         SMALLINT     NOT NULL,
    trimestre        SMALLINT     NOT NULL,
    mes              SMALLINT     NOT NULL,
    nombre_mes       VARCHAR(15)  NOT NULL,
    nombre_mes_corto VARCHAR(4)   NOT NULL,
    anio_mes         CHAR(7)      NOT NULL,      -- 'AAAA-MM'
    etiqueta_trim    VARCHAR(8)   NOT NULL,      -- '2024-T1'
    dia_del_mes      SMALLINT     NOT NULL,
    es_fin_trimestre BOOLEAN      NOT NULL,
    es_fin_anio      BOOLEAN      NOT NULL,
    es_cierre_fiscal BOOLEAN      NOT NULL
);
COMMENT ON TABLE dw_knime.dim_tiempo IS 'D1. Calendario de cortes mensuales. Jerarquía Año>Semestre>Trimestre>Mes.';

-- =====================================================================
-- DIMENSIÓN 2: ENTIDAD FINANCIERA   ***  SCD TIPO 2  ***
-- Historifica el cambio de estado (ACTIVA -> EN LIQUIDACIÓN).
-- Jerarquía: Grupo de tamaño > Perfil de negocio > Entidad
-- =====================================================================
CREATE TABLE dw_knime.dim_entidad (
    entidad_sk         SERIAL       PRIMARY KEY,
    cod_entidad        VARCHAR(30)  NOT NULL,    -- clave de negocio (natural key)
    nombre_entidad     VARCHAR(120) NOT NULL,    -- nombre crudo del origen
    nombre_comercial   VARCHAR(120) NOT NULL,    -- limpio: sin prefijos/sufijos/dobles espacios
    estado_entidad     VARCHAR(20)  NOT NULL,    -- ACTIVA | EN LIQUIDACION
    grupo_tamanio      VARCHAR(15),              -- GRANDE | MEDIANO | PEQUENO  (derivado)
    perfil_negocio     VARCHAR(20),              -- MICROFINANZAS|CONSUMO|COMERCIAL|VIVIENDA|MIXTO
    cobertura_geo      VARCHAR(15),              -- NACIONAL | REGIONAL | LOCAL (derivado)
    num_provincias     SMALLINT,
    num_cantones       SMALLINT,
    -- Atributos SCD Tipo 2
    version            SMALLINT     NOT NULL DEFAULT 1,
    fecha_inicio_vig   DATE         NOT NULL,
    fecha_fin_vig      DATE         NOT NULL DEFAULT DATE '9999-12-31',
    es_vigente         BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT uqk_entidad_version UNIQUE (cod_entidad, version)
);
COMMENT ON TABLE dw_knime.dim_entidad IS
  'D2. Bancos privados. SCD Tipo 2 sobre estado_entidad: se abre versión cuando la entidad entra en liquidación.';

-- =====================================================================
-- DIMENSIÓN 3: GEOGRAFÍA
-- Jerarquía: Región > Provincia > Cantón
-- =====================================================================
CREATE TABLE dw_knime.dim_geografia (
    geografia_sk       SERIAL       PRIMARY KEY,
    cod_geografia      VARCHAR(60)  NOT NULL UNIQUE,
    canton             VARCHAR(80)  NOT NULL,
    provincia          VARCHAR(80)  NOT NULL,
    region             VARCHAR(20)  NOT NULL,    -- COSTA|SIERRA|AMAZONICA|INSULAR|NO DEFINIDA
    nivel_bancarizacion VARCHAR(10),             -- ALTA|MEDIA|BAJA (derivado: nº de bancos presentes)
    num_entidades_presentes SMALLINT,
    es_canton_principal   BOOLEAN   DEFAULT FALSE,
    es_registro_desconocido BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE dw_knime.dim_geografia IS
  'D3. Jerarquía Región>Provincia>Cantón. La región se recupera por lookup desde la fuente PostgreSQL (Cartera no la trae).';

-- =====================================================================
-- DIMENSIÓN 4: PRODUCTO FINANCIERO
-- Jerarquía: Familia > Subfamilia > Producto
-- =====================================================================
CREATE TABLE dw_knime.dim_producto (
    producto_sk       SERIAL       PRIMARY KEY,
    cod_producto      VARCHAR(40)  NOT NULL UNIQUE,
    nombre_producto   VARCHAR(80)  NOT NULL,
    familia           VARCHAR(20)  NOT NULL,     -- CARTERA | DEPOSITO
    subfamilia        VARCHAR(40)  NOT NULL,     -- CREDITO COMERCIAL / VISTA / PLAZO ...
    cuenta_contable   VARCHAR(20),               -- código SB (ej. 210135)
    es_a_la_vista     BOOLEAN      DEFAULT FALSE,
    plazo_dias_min    SMALLINT,
    plazo_dias_max    SMALLINT,
    orden_presentacion SMALLINT
);
COMMENT ON TABLE dw_knime.dim_producto IS
  'D4. 6 segmentos de crédito + 13 tipos de depósito unificados en un solo eje de producto.';

-- =====================================================================
-- DIMENSIÓN 5: TIPO DE OPERACIÓN
-- Eje que permite comparar el negocio activo vs. pasivo del banco.
-- =====================================================================
CREATE TABLE dw_knime.dim_tipo_operacion (
    tipo_operacion_sk SERIAL      PRIMARY KEY,
    cod_operacion     VARCHAR(20) NOT NULL UNIQUE,
    nombre_operacion  VARCHAR(40) NOT NULL,      -- COLOCACION | CAPTACION
    naturaleza        VARCHAR(20) NOT NULL,      -- ACTIVO | PASIVO
    descripcion       VARCHAR(160)
);
COMMENT ON TABLE dw_knime.dim_tipo_operacion IS
  'D5. Distingue el lado activo (colocaciones/crédito) del pasivo (captaciones/depósitos).';

-- =====================================================================
-- DIMENSIÓN 6: FUENTE DE DATOS  (linaje / auditoría)
-- Deja evidencia en el DW de cuál de las 4 fuentes originó cada hecho.
-- =====================================================================
CREATE TABLE dw_knime.dim_fuente_datos (
    fuente_sk        SERIAL       PRIMARY KEY,
    cod_fuente       VARCHAR(20)  NOT NULL UNIQUE,
    nombre_fuente    VARCHAR(60)  NOT NULL,
    tipo_tecnologia  VARCHAR(30)  NOT NULL,      -- PostgreSQL|MySQL|Excel XLSX|CSV
    sistema_origen   VARCHAR(80),
    formato_archivo  VARCHAR(20),
    descripcion      VARCHAR(200)
);
COMMENT ON TABLE dw_knime.dim_fuente_datos IS
  'D6. Trazabilidad: identifica la tecnología de origen (PostgreSQL, MySQL, Excel, CSV) de cada fila de hechos.';

-- =====================================================================
-- TABLA DE HECHOS: SALDOS FINANCIEROS
-- Grano: un registro por  fecha de corte x entidad x cantón x producto
-- Tipo : snapshot periódico mensual (semi-aditivo en el tiempo)
-- =====================================================================
CREATE TABLE dw_knime.fact_saldos_financieros (
    saldo_sk           BIGSERIAL PRIMARY KEY,
    -- ---- Claves foráneas a las 6 dimensiones ----
    tiempo_sk          INTEGER   NOT NULL REFERENCES dw_knime.dim_tiempo(tiempo_sk),
    entidad_sk         INTEGER   NOT NULL REFERENCES dw_knime.dim_entidad(entidad_sk),
    geografia_sk       INTEGER   NOT NULL REFERENCES dw_knime.dim_geografia(geografia_sk),
    producto_sk        INTEGER   NOT NULL REFERENCES dw_knime.dim_producto(producto_sk),
    tipo_operacion_sk  INTEGER   NOT NULL REFERENCES dw_knime.dim_tipo_operacion(tipo_operacion_sk),
    fuente_sk          INTEGER   NOT NULL REFERENCES dw_knime.dim_fuente_datos(fuente_sk),
    -- ---- Métricas comunes ----
    saldo_total        NUMERIC(20,2) NOT NULL DEFAULT 0,
    -- ---- Métricas exclusivas de COLOCACIONES (cartera) ----
    saldo_por_vencer   NUMERIC(20,2),
    saldo_no_devenga   NUMERIC(20,2),
    saldo_vencido      NUMERIC(20,2),
    saldo_improductivo NUMERIC(20,2),            -- calculada: no_devenga + vencido
    -- ---- Métricas exclusivas de CAPTACIONES (depósitos) ----
    numero_cuentas     BIGINT,
    numero_clientes    BIGINT,
    saldo_promedio_cliente NUMERIC(20,2),        -- calculada: saldo / clientes
    -- ---- Auditoría ----
    fecha_carga        TIMESTAMP DEFAULT now(),
    CONSTRAINT ckk_saldo_no_negativo CHECK (saldo_total >= 0)
);

COMMENT ON TABLE dw_knime.fact_saldos_financieros IS
  'Tabla de hechos. Snapshot mensual de saldos de colocaciones y captaciones de la banca privada ecuatoriana.';

-- Índices para el desempeño del cubo OLAP (una por FK + compuesto de uso frecuente)
CREATE INDEX ixk_fact_tiempo    ON dw_knime.fact_saldos_financieros (tiempo_sk);
CREATE INDEX ixk_fact_entidad   ON dw_knime.fact_saldos_financieros (entidad_sk);
CREATE INDEX ixk_fact_geografia ON dw_knime.fact_saldos_financieros (geografia_sk);
CREATE INDEX ixk_fact_producto  ON dw_knime.fact_saldos_financieros (producto_sk);
CREATE INDEX ixk_fact_operacion ON dw_knime.fact_saldos_financieros (tipo_operacion_sk);
CREATE INDEX ixk_fact_fuente    ON dw_knime.fact_saldos_financieros (fuente_sk);
CREATE INDEX ixk_fact_cubo      ON dw_knime.fact_saldos_financieros (tiempo_sk, tipo_operacion_sk, entidad_sk);
