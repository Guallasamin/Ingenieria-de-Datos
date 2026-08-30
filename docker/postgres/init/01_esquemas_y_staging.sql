-- =====================================================================
-- FUENTE 1: PostgreSQL  |  Capa STAGING (réplica del sistema origen)
-- Taller Individual Semana 1 - Ingeniería de Datos
-- ---------------------------------------------------------------------
-- Arquitectura de 2 capas dentro del mismo motor:
--   staging -> datos crudos tal como salen del origen (sin transformar)
--   dw      -> modelo estrella (ver 02_ddl_dw_estrella.sql)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION etl_user;
CREATE SCHEMA IF NOT EXISTS dw      AUTHORIZATION etl_user;

COMMENT ON SCHEMA staging IS 'Capa de aterrizaje: copia fiel de los sistemas origen, sin limpieza.';
COMMENT ON SCHEMA dw      IS 'Data Warehouse - modelo estrella (Kimball).';

-- ---------------------------------------------------------------------
-- staging.captaciones_banca_privada
-- Origen: Superintendencia de Bancos del Ecuador
--         "CAPTACIONES BANCA PRIVADA" (hoja BASE BANCA PRIVADA)
-- Grano : fecha x entidad x cantón x cuenta contable x tipo de depósito
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS staging.captaciones_banca_privada;
CREATE TABLE staging.captaciones_banca_privada (
    id_registro       BIGSERIAL      PRIMARY KEY,
    fecha_corte       DATE           NOT NULL,
    entidad           VARCHAR(120)   NOT NULL,
    region            VARCHAR(40),
    provincia         VARCHAR(80),
    canton            VARCHAR(80),
    cuenta_contable   VARCHAR(20),
    tipo_deposito     VARCHAR(80),
    numero_cuentas    BIGINT,
    numero_clientes   BIGINT,
    saldo             NUMERIC(20,2),
    -- metadatos de linaje (auditoría ETL)
    archivo_origen    VARCHAR(200),
    anio_archivo      SMALLINT,
    fecha_carga       TIMESTAMP      DEFAULT now()
);

COMMENT ON TABLE staging.captaciones_banca_privada IS
    'FUENTE 1 (PostgreSQL). Depósitos del sistema de banca privada del Ecuador, 2024-01 a 2026-05.';

CREATE INDEX ix_capt_fecha    ON staging.captaciones_banca_privada (fecha_corte);
CREATE INDEX ix_capt_entidad  ON staging.captaciones_banca_privada (entidad);
CREATE INDEX ix_capt_geo      ON staging.captaciones_banca_privada (provincia, canton);
CREATE INDEX ix_capt_tipo     ON staging.captaciones_banca_privada (tipo_deposito);

-- ---------------------------------------------------------------------
-- Bitácora de ejecuciones del ETL (auditoría)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS staging.etl_bitacora;
CREATE TABLE staging.etl_bitacora (
    id_ejecucion     BIGSERIAL   PRIMARY KEY,
    proceso          VARCHAR(80) NOT NULL,
    fuente           VARCHAR(40),
    objeto_destino   VARCHAR(120),
    filas_leidas     BIGINT,
    filas_escritas   BIGINT,
    filas_rechazadas BIGINT DEFAULT 0,
    estado           VARCHAR(20),
    mensaje          TEXT,
    inicio           TIMESTAMP   DEFAULT now(),
    fin              TIMESTAMP
);

COMMENT ON TABLE staging.etl_bitacora IS 'Bitácora de auditoría: cada corrida del ETL deja traza aquí.';
