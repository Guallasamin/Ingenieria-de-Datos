-- =====================================================================
-- FUENTE 2: MySQL  |  Catálogos maestros del negocio
-- ---------------------------------------------------------------------
-- Simula el "sistema maestro" corporativo: las tablas de referencia que
-- alimentan las dimensiones. El ETL las lee vía conector MySQL de KNIME.
-- =====================================================================
CREATE DATABASE IF NOT EXISTS catalogos_sb
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE catalogos_sb;

-- ---------------------------------------------------------------------
-- Catálogo de entidades financieras -> alimenta dw.dim_entidad
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS cat_entidad_financiera;
CREATE TABLE cat_entidad_financiera (
    entidad_sk        INT          NOT NULL PRIMARY KEY,
    cod_entidad       VARCHAR(30)  NOT NULL,
    version           SMALLINT     NOT NULL DEFAULT 1,
    fecha_inicio_vig  DATE         NOT NULL,
    fecha_fin_vig     DATE         NOT NULL,
    es_vigente        TINYINT(1)   NOT NULL DEFAULT 1,
    nombre_entidad    VARCHAR(120) NOT NULL,
    nombre_comercial  VARCHAR(120) NOT NULL,
    estado_entidad    VARCHAR(20)  NOT NULL,
    grupo_tamanio     VARCHAR(15),
    perfil_negocio    VARCHAR(20),
    cobertura_geo     VARCHAR(15),
    num_provincias    SMALLINT,
    num_cantones      SMALLINT,
    fecha_alta        DATE,
    UNIQUE KEY uq_entidad_version (cod_entidad, version),
    KEY ix_estado (estado_entidad),
    KEY ix_tamanio (grupo_tamanio)
) ENGINE=InnoDB COMMENT='Maestro de bancos privados. Atributos derivados del perfilado de las fuentes.';

-- ---------------------------------------------------------------------
-- Catálogo geográfico -> alimenta dw.dim_geografia
-- Resuelve el problema de que Cartera NO trae la columna REGION.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS cat_geografia;
CREATE TABLE cat_geografia (
    geografia_sk            INT         NOT NULL PRIMARY KEY,
    cod_geografia           VARCHAR(60) NOT NULL,
    canton                  VARCHAR(80) NOT NULL,
    provincia               VARCHAR(80) NOT NULL,
    region                  VARCHAR(20) NOT NULL,
    nivel_bancarizacion     VARCHAR(10),
    num_entidades_presentes SMALLINT,
    es_canton_principal     TINYINT(1) DEFAULT 0,
    es_registro_desconocido TINYINT(1) DEFAULT 0,
    UNIQUE KEY uq_geo (cod_geografia),
    KEY ix_prov (provincia),
    KEY ix_region (region)
) ENGINE=InnoDB COMMENT='Jerarquía Región>Provincia>Cantón del Ecuador (126 cantones con presencia bancaria).';

-- ---------------------------------------------------------------------
-- Catálogo de productos financieros -> alimenta dw.dim_producto
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS cat_producto_financiero;
CREATE TABLE cat_producto_financiero (
    producto_sk        INT         NOT NULL PRIMARY KEY,
    cod_producto       VARCHAR(40) NOT NULL,
    nombre_producto    VARCHAR(80) NOT NULL,
    familia            VARCHAR(20) NOT NULL,
    subfamilia         VARCHAR(40) NOT NULL,
    cuenta_contable    VARCHAR(20),
    es_a_la_vista      TINYINT(1) DEFAULT 0,
    plazo_dias_min     SMALLINT,
    plazo_dias_max     SMALLINT,
    orden_presentacion SMALLINT,
    UNIQUE KEY uq_prod (cod_producto),
    KEY ix_familia (familia)
) ENGINE=InnoDB COMMENT='6 segmentos de crédito + 13 tipos de depósito.';

-- ---------------------------------------------------------------------
-- Catálogo de tipo de operación -> alimenta dw.dim_tipo_operacion
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS cat_tipo_operacion;
CREATE TABLE cat_tipo_operacion (
    tipo_operacion_sk INT        NOT NULL PRIMARY KEY,
    cod_operacion    VARCHAR(20) NOT NULL UNIQUE,
    nombre_operacion VARCHAR(40) NOT NULL,
    naturaleza       VARCHAR(20) NOT NULL,
    descripcion      VARCHAR(160)
) ENGINE=InnoDB;

INSERT INTO cat_tipo_operacion VALUES
 (1,'COL','COLOCACION','ACTIVO',
  'Crédito concedido por la entidad. Constituye el activo productivo del banco.'),
 (2,'CAP','CAPTACION','PASIVO',
  'Recursos del público depositados en la entidad. Constituye el pasivo con costo.');

-- ---------------------------------------------------------------------
-- Catálogo de fuentes de datos -> alimenta dw.dim_fuente_datos
-- Documenta formalmente las 4 fuentes heterogéneas del taller.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS cat_fuente_datos;
CREATE TABLE cat_fuente_datos (
    fuente_sk       INT         NOT NULL PRIMARY KEY,
    cod_fuente      VARCHAR(20) NOT NULL UNIQUE,
    nombre_fuente   VARCHAR(60) NOT NULL,
    tipo_tecnologia VARCHAR(30) NOT NULL,
    sistema_origen  VARCHAR(80),
    formato_archivo VARCHAR(20),
    descripcion     VARCHAR(200)
) ENGINE=InnoDB;

INSERT INTO cat_fuente_datos VALUES
 (1,'F1_POSTGRES','Captaciones banca privada','PostgreSQL',
  'Superintendencia de Bancos del Ecuador','Tabla relacional',
  'FUENTE 1: 122.217 registros de depósitos 2024-2026 en staging.captaciones_banca_privada.'),
 (2,'F2_MYSQL','Catálogos maestros','MySQL',
  'Sistema maestro corporativo','Tablas relacionales',
  'FUENTE 2: catálogos de entidad, geografía, producto, operación y linaje.'),
 (3,'F3_EXCEL','Colocaciones 2024-2025','Excel XLSX',
  'Superintendencia de Bancos del Ecuador','.xlsx',
  'FUENTE 3: 10 libros Excel con la cartera por segmento de los años 2024 y 2025.'),
 (4,'F4_CSV','Colocaciones 2026','CSV',
  'Superintendencia de Bancos del Ecuador','.csv (UTF-8, ;)',
  'FUENTE 4: extracto plano de la cartera de enero a mayo de 2026.');
