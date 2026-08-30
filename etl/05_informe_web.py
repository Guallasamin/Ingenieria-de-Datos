#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PASO 5 - Version web del informe ejecutivo (informe/artefacto.html).
Reutiliza los graficos y consultas de 04_informe.py, pero con tokens CSS
para que la pagina funcione en tema claro y oscuro.
Ejecucion: docker exec etl_runtime python etl/05_informe_web.py
"""
import os, sys
sys.path.insert(0, "/proyecto/etl")
import importlib.util
spec = importlib.util.spec_from_file_location("inf", os.path.join(os.path.dirname(os.path.abspath(__file__)), "04_informe.py"))
inf = importlib.util.module_from_spec(spec); spec.loader.exec_module(inf)
q, mil, es_num = inf.q, inf.mil, inf.es_num

# --- series de grafico: slots 1 y 2 de la paleta validada, via tokens CSS ---
inf.AZUL, inf.NARANJA = "var(--s1)", "var(--s2)"
inf.ROJO = "var(--s2)"
inf.TINTA, inf.TINTA2, inf.TINTA3 = "var(--ink)", "var(--ink-2)", "var(--ink-3)"
inf.GRID, inf.BORDE = "var(--rule)", "var(--rule)"

n_fact = int(q("SELECT COUNT(*) n FROM dw.fact_saldos_financieros").n[0])
conteos = q("""SELECT 'dim_tiempo' o,'Cortes mensuales, ene-2024 a may-2026' d, COUNT(*) n FROM dw.dim_tiempo
  UNION ALL SELECT 'dim_entidad','25 bancos · 1 version historica SCD2', COUNT(*) FROM dw.dim_entidad
  UNION ALL SELECT 'dim_geografia','5 regiones · 25 provincias · cantones', COUNT(*) FROM dw.dim_geografia
  UNION ALL SELECT 'dim_producto','6 segmentos de credito + 13 tipos de deposito', COUNT(*) FROM dw.dim_producto
  UNION ALL SELECT 'dim_tipo_operacion','Colocacion (activo) / Captacion (pasivo)', COUNT(*) FROM dw.dim_tipo_operacion
  UNION ALL SELECT 'dim_fuente_datos','Linaje: PostgreSQL, MySQL, Excel, CSV', COUNT(*) FROM dw.dim_fuente_datos""")
top = q("""SELECT entidad e, grupo_tamanio g,
        TO_CHAR(SUM(saldo_total)/1e6,'FM999G999G990D0') s, TO_CHAR(SUM(numero_clientes),'FM999G999G999') c
     FROM dw.v_cubo_banca WHERE anio_mes='2026-05' AND naturaleza='PASIVO'
     GROUP BY 1,2 ORDER BY SUM(saldo_total) DESC LIMIT 6""")
conc = q("""SELECT grupo_tamanio g, COUNT(DISTINCT entidad) b,
        ROUND(100.0*SUM(saldo_total)/SUM(SUM(saldo_total)) OVER (),1) p
     FROM dw.v_cubo_banca WHERE anio_mes='2026-05' AND naturaleza='PASIVO' GROUP BY 1 ORDER BY 3 DESC""")
kn = q("""SELECT
  (SELECT COUNT(*) FROM dw_knime.fact_saldos_financieros) f_kn,
  (SELECT COUNT(*) FROM dw.fact_saldos_financieros)       f_py""").iloc[0]
mor = q("SELECT anio a, ROUND(100.0*SUM(cartera_improductiva)/SUM(cartera_bruta),2) p "
        "FROM dw.v_kpi_morosidad GROUP BY 1 ORDER BY 1")
FUENTES = [("01","PostgreSQL","staging.captaciones_banca_privada","122.217","Tabla de hechos"),
           ("02","MySQL","catalogos_sb — 5 catálogos maestros","177","Dimensiones"),
           ("03","Excel XLSX","10 libros de cartera 2024–2025, hoja BASE","45.341","Tabla de hechos"),
           ("04","CSV","colocaciones_2026.csv, delimitador ;","9.432","Tabla de hechos")]
LIMPIEZA = [("Espacios múltiples","<code>BP BANCO&nbsp;&nbsp;DESARROLLO DE LOS PUEBLOS&nbsp;&nbsp;S.A.</code> contiene espacios dobles en la razón social.","Colapso con <code>regexReplace(strip(col), \"\\\\s+\", \" \")</code>."),
  ("Prefijos heterogéneos","El regulador antepone <code>BP</code> a unas entidades y <code>BANCO</code> a otras; algunas arrastran <code>S.A.</code>","Derivación de un nombre comercial homogéneo, base de la clave de negocio <code>cod_entidad</code>."),
  ("Diacríticos en claves","<code>ATLÁNTIDA</code>, <code>CAÑAR</code> y <code>TSÁCHILAS</code> contienen diacríticos que impiden el cruce entre fuentes.","Normalización NFD para la clave; las tildes se conservan en el nombre de presentación."),
  ("Región ausente","Los archivos de cartera no incluyen la columna <code>REGIÓN</code>, presente en los de depósitos.","<i>Join</i> contra el catálogo geográfico alojado en MySQL; la dimensión se construye con dos fuentes."),
  ("Miembro huérfano","<code>ZONA NO DELIMITADA / LAS GOLONDRINAS</code> figura en cartera pero no en depósitos, por lo que carece de región asignable.","Miembro <code>NO DEFINIDA</code> y bandera <code>es_registro_desconocido</code>; las 58 filas conservan sus importes."),
  ("Entidad en liquidación","<code>BANCO AMIBANK S.A.</code> y <code>…, EN LIQUIDACION</code> son la misma institución en dos momentos.","Dimensión lentamente cambiante de tipo 2: una clave de negocio y dos versiones con vigencia acotada.")]

def fila_fuente(n,t,d,f,a):
    return f'''<tr><td class="num-col">{n}</td><td><b>{t}</b></td><td class="muted">{d}</td>
      <td class="n">{f}</td><td><span class="chip">{a}</span></td></tr>'''

kpi_mor = " · ".join(f"{int(r.a)} {es_num(r.p)} %" for _, r in mor.iterrows())

HTML = f"""<title>Banca privada en estrella</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Arimo:ital,wght@0,400;0,500;0,600;0,700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  /* Identidad USFQ: negro y rojo institucionales sobre fondo crema */
  --paper:#faf3e9; --surface:#ffffff; --surface-2:#f4ece0;
  --ink:#231f20; --ink-2:#4a4b4c; --ink-3:#8a8b8c;
  --rule:#e3ded4; --rule-2:#d8d4cb;
  --accent:#b3141a; --accent-soft:#fbe9ea;
  --warm:#ed1c24; --warm-soft:#fbe9ea;
  --ok:#1a7048;
  --s1:#231f20; --s2:#ed1c24;
  --shadow:0 1px 2px rgba(18,23,29,.06), 0 8px 24px -12px rgba(18,23,29,.18);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:#141210; --surface:#1d1a18; --surface-2:#252120;
    --ink:#f2ece4; --ink-2:#b3aca4; --ink-3:#7d766f;
    --rule:#332e2b; --rule-2:#453e3a;
    --accent:#f4565c; --accent-soft:#2a1618;
    --warm:#f4565c; --warm-soft:#2a1618;
    --ok:#4fae82;
    --s1:#e8e2da; --s2:#f4565c;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }}
}}
:root[data-theme="dark"] {{
  --paper:#141210; --surface:#1d1a18; --surface-2:#252120;
  --ink:#f2ece4; --ink-2:#b3aca4; --ink-3:#7d766f;
  --rule:#332e2b; --rule-2:#453e3a;
  --accent:#f4565c; --accent-soft:#2a1618;
  --warm:#f4565c; --warm-soft:#2a1618;
  --ok:#4fae82;
  --s1:#e8e2da; --s2:#f4565c;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:Helvetica,"Helvetica Neue",Arimo,Arial,sans-serif;
  font-size:16px; line-height:1.62; -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:1080px; margin:0 auto; padding:0 24px 96px; }}

/* ---------- cabecera ---------- */
header.hero {{ padding:72px 0 40px; border-bottom:1px solid var(--rule); }}
.eyebrow {{
  font-size:11.5px; font-weight:600; letter-spacing:.16em; text-transform:uppercase;
  color:var(--accent); margin-bottom:20px;
}}
h1 {{
  font-family:Baskerville,"Baskerville Old Face","Libre Baskerville",Garamond,serif; font-weight:700; font-size:clamp(30px,4.4vw,50px);
  line-height:1.12; letter-spacing:-.015em; margin:0 0 18px; text-wrap:balance; max-width:19ch;
}}
.standfirst {{
  font-family:Baskerville,"Baskerville Old Face","Libre Baskerville",Garamond,serif; font-size:clamp(17px,2vw,20px); line-height:1.55;
  color:var(--ink-2); max-width:60ch; margin:0 0 34px;
}}
.metagrid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:1px;
  background:var(--rule); border:1px solid var(--rule); border-radius:8px; overflow:hidden; }}
.metagrid div {{ background:var(--surface); padding:14px 16px; }}
.metagrid dt {{ font-size:11px; font-weight:600; letter-spacing:.09em; text-transform:uppercase;
  color:var(--ink-3); margin-bottom:5px; }}
.metagrid dd {{ margin:0; font-size:14.5px; font-weight:500; }}

/* ---------- indicadores ---------- */
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:14px; margin:34px 0 0; }}
.kpi {{ background:var(--surface); border:1px solid var(--rule); border-radius:10px;
  padding:18px 20px; box-shadow:var(--shadow); }}
.kpi .v {{ font-family:Baskerville,"Baskerville Old Face","Libre Baskerville",Garamond,serif; font-size:34px; font-weight:700;
  line-height:1; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }}
.kpi .l {{ font-size:12.5px; color:var(--ink-2); margin-top:9px; line-height:1.4; }}
.kpi.is-ok .v {{ color:var(--ok); }}

/* ---------- secciones con lomo numerado ---------- */
section {{ display:grid; grid-template-columns:56px minmax(0,1fr); gap:0 28px;
  padding-top:56px; }}
.spine {{ font-family:"IBM Plex Mono",Consolas,monospace; font-size:12px; font-weight:500;
  color:var(--ink-3); padding-top:9px; position:sticky; top:20px; align-self:start;
  border-top:2px solid var(--accent); }}
.body-col {{ min-width:0; }}
h2 {{ font-family:Baskerville,"Baskerville Old Face","Libre Baskerville",Garamond,serif; font-size:clamp(23px,2.9vw,31px); font-weight:600;
  letter-spacing:-.012em; line-height:1.2; margin:0 0 16px; text-wrap:balance; }}
h3 {{ font-size:16px; font-weight:700; margin:32px 0 9px; letter-spacing:-.005em; }}
p {{ margin:0 0 15px; max-width:66ch; }}
.muted {{ color:var(--ink-2); }}
ul,ol {{ max-width:66ch; padding-left:20px; margin:0 0 15px; }}
li {{ margin-bottom:8px; }}
code {{ font-family:"IBM Plex Mono",Consolas,monospace; font-size:.855em; background:var(--surface-2);
  padding:2px 5px; border-radius:4px; border:1px solid var(--rule); }}
pre {{ font-family:"IBM Plex Mono",Consolas,monospace; font-size:13px; line-height:1.65;
  background:var(--surface); border:1px solid var(--rule); border-left:3px solid var(--accent);
  border-radius:8px; padding:16px 18px; overflow-x:auto; margin:0 0 18px; }}
pre code {{ background:none; border:0; padding:0; font-size:inherit; }}

/* ---------- tablas ---------- */
.tw {{ overflow-x:auto; margin:0 0 20px; border:1px solid var(--rule);
  border-radius:9px; background:var(--surface); }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; font-size:11.5px; font-weight:600; letter-spacing:.075em;
  text-transform:uppercase; color:var(--ink-3); padding:12px 16px;
  border-bottom:1px solid var(--rule-2); white-space:nowrap; background:var(--surface-2); }}
td {{ padding:11px 16px; border-bottom:1px solid var(--rule); vertical-align:top; }}
tbody tr:last-child td {{ border-bottom:0; }}
td.n, th.n {{ text-align:right; font-variant-numeric:tabular-nums;
  font-family:"IBM Plex Mono",Consolas,monospace; font-size:13px; white-space:nowrap; }}
.num-col {{ font-family:"IBM Plex Mono",Consolas,monospace; font-size:12px; color:var(--ink-3); }}
.chip {{ display:inline-block; font-size:11.5px; font-weight:600; padding:3px 9px;
  border-radius:20px; background:var(--accent-soft); color:var(--accent); white-space:nowrap; }}
.chip.warm {{ background:var(--warm-soft); color:var(--warm); }}
code.k {{ font-size:12.5px; }}

/* ---------- figuras ---------- */
figure {{ margin:22px 0 26px; }}
.figbox {{ background:var(--surface); border:1px solid var(--rule); border-radius:10px;
  padding:20px 22px; overflow-x:auto; }}
figcaption {{ font-size:12.5px; color:var(--ink-3); margin-top:11px; max-width:70ch;
  line-height:1.5; }}
figcaption b {{ color:var(--ink-2); font-weight:600; }}

/* ---------- callout ---------- */
.callout {{ border-left:3px solid var(--warm); background:var(--surface); border-radius:0 8px 8px 0;
  padding:16px 20px; margin:0 0 20px; font-size:14.5px; max-width:66ch;
  border-top:1px solid var(--rule); border-right:1px solid var(--rule);
  border-bottom:1px solid var(--rule); }}
.callout b {{ color:var(--warm); }}

@media (max-width:640px) {{
  section {{ grid-template-columns:1fr; gap:0; }}
  .spine {{ position:static; border-top:0; padding:0 0 8px; }}
  .fix > div {{ grid-template-columns:1fr; }}
  .fix .sol {{ grid-column:1; }}
}}
footer {{ margin-top:64px; padding-top:24px; border-top:1px solid var(--rule);
  font-size:13px; color:var(--ink-3); display:flex; flex-wrap:wrap; gap:6px 20px; }}
svg {{ display:block; max-width:100%; height:auto; }}
</style>

<div class="wrap">

<header class="hero">
  <div class="eyebrow">Universidad San Francisco de Quito · Ingeniería de Datos</div>
  <h1>Flujo ETL multifuente y Data Warehouse dimensional del sistema de banca privada del Ecuador</h1>
  <p class="standfirst">Informe técnico. Integración de cuatro fuentes de datos heterogéneas
  —PostgreSQL, MySQL, Excel y CSV— en un modelo estrella de seis dimensiones y una tabla de
  hechos, sobre infraestructura contenerizada.</p>
  <dl class="metagrid">
    <div><dt>Fuente de los datos</dt><dd>Superintendencia de Bancos del Ecuador</dd></div>
    <div><dt>Periodo</dt><dd>ene 2024 – may 2026 · 29 cortes</dd></div>
    <div><dt>Motor del DW</dt><dd>PostgreSQL 16 · esquema <code class="k">dw</code></dd></div>
    <div><dt>Orquestación</dt><dd>KNIME · 122 nodos</dd></div>
  </dl>
  <div class="kpis">
    <div class="kpi"><div class="v">4</div><div class="l">Fuentes de datos integradas</div></div>
    <div class="kpi"><div class="v">6<span style="color:var(--ink-3)">+</span>1</div><div class="l">Dimensiones y tabla de hechos</div></div>
    <div class="kpi"><div class="v">{mil(n_fact)}</div><div class="l">Registros de hechos cargados</div></div>
    <div class="kpi is-ok"><div class="v">0</div><div class="l">Registros huérfanos y filas descuadradas</div></div>
  </div>
</header>

<section>
  <div class="spine">01</div>
  <div class="body-col">
    <h2>Objeto y alcance</h2>
    <p>El conjunto de entrada consta de 18 libros Excel publicados por la Superintendencia de
    Bancos del Ecuador, con el detalle mensual de la cartera de crédito y de los depósitos de las
    26 razones sociales de la banca privada, desagregado hasta el nivel cantonal. La información
    se distribuye en cuatro tecnologías de origen distintas y se consolida en un Data Warehouse
    dimensional.</p>
    <p>El proceso carga <b>{mil(n_fact)} registros</b> en la tabla de hechos y registra cero
    violaciones de integridad referencial. La infraestructura se despliega mediante
    <code>docker compose up</code>.</p>

    <figure>
      <div class="figbox">{inf.diagrama_arquitectura()}</div>
      <figcaption><b>Figura 1.</b> Arquitectura de extremo a extremo: cuatro fuentes, transformación
      en KNIME, modelo estrella en PostgreSQL y capa de explotación OLAP.</figcaption>
    </figure>
  </div>
</section>

<section>
  <div class="spine">02</div>
  <div class="body-col">
    <h2>Fuentes de datos</h2>
    <p>Cada libro del regulador contiene dos hojas: una de presentación, con subtotales embebidos
    y celdas combinadas, y una hoja <code>BASE</code> en formato largo. El flujo lee la hoja
    <code>BASE</code>; la hoja de presentación duplicaría los importes al mezclar registros de
    detalle con filas de totales.</p>
    <div class="tw"><table>
      <thead><tr><th>#</th><th>Tecnología</th><th>Contenido</th><th class="n">Filas</th><th>Alimenta</th></tr></thead>
      <tbody>{"".join(fila_fuente(*f) for f in FUENTES)}</tbody>
    </table></div>
    <div class="callout"><b>Distribución de las fuentes.</b> Las captaciones, que constituyen el
    conjunto de mayor volumen, residen en PostgreSQL. Los catálogos maestros residen en MySQL. La
    cartera de 2024 y 2025 se lee directamente de los libros Excel originales, sin conversión
    previa. La cartera de 2026 se entrega en formato CSV. Cada fuente requiere un conector
    distinto en KNIME.</div>
    <p>Cada libro del regulador contiene una hoja de presentación, con subtotales embebidos, y
    una hoja <code>BASE</code> en formato largo. El flujo lee la hoja <code>BASE</code>. El
    perfilado previo registró cero valores nulos y cero importes negativos, y verificó que la
    identidad <code>TOTAL = POR VENCER + NO DEVENGA + VENCIDA</code> se cumple en las 54.773 filas
    de cartera.</p>
  </div>
</section>

<section>
  <div class="spine">03</div>
  <div class="body-col">
    <h2>Diseño del Data Warehouse</h2>
    <p>El modelo unifica colocaciones y captaciones en una única tabla de hechos y emplea la
    dimensión <code>dim_tipo_operacion</code> como eje discriminador. Esta configuración permite
    calcular indicadores que cruzan el activo y el pasivo de la entidad, como el ratio de
    intermediación financiera, sin unir dos tablas de hechos distintas.</p>
    <figure>
      <div class="figbox">{inf.diagrama_estrella(mil(n_fact))}</div>
      <figcaption><b>Figura 2.</b> Seis dimensiones conformadas alrededor de la tabla de hechos.
      Todas las claves primarias son subrogadas.</figcaption>
    </figure>
    <p><b>Grano:</b> un registro por mes de corte, entidad, cantón y producto financiero. La tabla
    corresponde a un <i>snapshot</i> periódico mensual, por lo que las métricas de saldo son
    semiaditivas en el tiempo: admiten agregación a través de entidades y territorios, pero no a lo
    largo de los meses, donde corresponde tomar el último corte.</p>
    <div class="tw"><table>
      <thead><tr><th>Dimensión</th><th>Contenido</th><th class="n">Filas</th></tr></thead>
      <tbody>{"".join(f'<tr><td><code class="k">{r.o}</code></td><td class="muted">{r.d}</td><td class="n">{mil(r.n)}</td></tr>' for _,r in conteos.iterrows())}
      <tr><td><code class="k">fact_saldos_financieros</code></td><td class="muted">Snapshot mensual de saldos</td><td class="n">{mil(n_fact)}</td></tr></tbody>
    </table></div>
    <h3>Jerarquías</h3>
    <ul>
      <li><b>Tiempo:</b> Año → Semestre → Trimestre → Mes</li>
      <li><b>Entidad:</b> Grupo de tamaño → Perfil de negocio → Entidad</li>
      <li><b>Geografía:</b> Región → Provincia → Cantón</li>
      <li><b>Producto:</b> Familia → Subfamilia → Producto</li>
    </ul>
    <p>Estas jerarquías habilitan las operaciones OLAP de <i>drill-down</i>, <i>roll-up</i> y
    <i>slice and dice</i>. La vista <code>dw.v_cubo_banca</code> expone el modelo desnormalizado;
    cuatro vistas adicionales materializan los indicadores de negocio.</p>
  </div>
</section>

<section>
  <div class="spine">04</div>
  <div class="body-col">
    <h2>El flujo en KNIME</h2>
    <p>El flujo <code>ETL_Banca_Ecuador.knwf</code> implementa el proceso completo con
    <b>122 nodos y 135 conexiones</b> en quince tipos de nodo distintos. Se ejecutó de
    extremo a extremo y carga el modelo estrella en el esquema <code>dw_knime</code>.</p>
    <div class="tw"><table>
      <thead><tr><th>Bloque</th><th class="n">Nodos</th><th>Contenido</th></tr></thead>
      <tbody>
        <tr><td><b>A. Extracción</b></td><td class="n">23</td><td class="muted">2 conectores de
          base de datos, 7 lectores de consulta, 12 lectores de Excel, 1 lector de CSV</td></tr>
        <tr><td><b>B. Transformación</b></td><td class="n">30</td><td class="muted">25 String
          Manipulation, 4 Math Formula, 4 Rule Engine, 4 Rule-based Row Filter,
          13 Concatenate</td></tr>
        <tr><td><b>C. Dimensiones</b></td><td class="n">20</td><td class="muted">Carga de las
          seis dimensiones; <code>dim_tiempo</code> se deriva dentro del propio flujo</td></tr>
        <tr><td><b>D. Hechos</b></td><td class="n">19</td><td class="muted">8 Joiner que
          sustituyen las claves de negocio por las subrogadas, incluido el lookup SCD-2</td></tr>
      </tbody>
    </table></div>
    <div class="callout"><b>Conciliación entre implementaciones.</b> El flujo de KNIME y el proceso
    de respaldo escrito en Python cargan {mil(kn.f_py)} registros de hechos cada uno, con saldos
    coincidentes. Las pruebas V9 y V10 de <code>etl/03_validacion.sql</code> contrastan ambos
    esquemas.</div>
  </div>
</section>

<section>
  <div class="spine">05</div>
  <div class="body-col">
    <h2>Transformación y limpieza</h2>
    <p>El perfilado identificó seis incidencias en los archivos de origen. A continuación se
    describe cada una y el tratamiento aplicado.</p>
    <div class="tw"><table>
      <thead><tr><th style="width:42%">Incidencia</th><th>Tratamiento</th></tr></thead>
      <tbody>{"".join(f'<tr><td>{d}</td><td class="muted">{t}</td></tr>' for _,d,t in LIMPIEZA)}</tbody>
    </table></div>
    <p>Durante la resolución de claves subrogadas, cada hecho se asocia a la versión de la entidad
    vigente en su fecha de corte. Los saldos anteriores a enero de 2025 quedan atribuidos a la
    entidad activa y los posteriores a la entidad en liquidación.</p>
    <div class="callout"><b>Filtro de calidad.</b> Se descartan las filas sin fecha, sin entidad o
    con saldo negativo. El número de filas descartadas es cero.</div>
  </div>
</section>

<section>
  <div class="spine">06</div>
  <div class="body-col">
    <h2>Validación</h2>
    <p>El script <code>etl/03_validacion.sql</code> ejecuta diez pruebas sobre el almacén cargado. Resultados obtenidos:</p>
    <ul>
      <li><b>Integridad referencial:</b> cero registros huérfanos en las seis claves foráneas.</li>
      <li><b>Conciliación con el origen:</b> 122.217 filas y USD 1.558.549 millones en
        <code>staging</code> y en el almacén; los valores coinciden.</li>
      <li><b>Regla contable:</b> cero filas incumplen la identidad
        TOTAL = POR VENCER + NO DEVENGA + VENCIDA.</li>
      <li><b>Trazabilidad:</b> cada registro de hechos conserva su fuente de origen mediante
        <code>dim_fuente_datos</code>.</li>
      <li><b>Cobertura temporal:</b> 29 cortes mensuales consecutivos, sin interrupciones.</li>
      <li><b>Conciliación entre implementaciones:</b> los esquemas <code>dw</code> y
        <code>dw_knime</code> presentan idéntico número de filas e idénticos importes en las
        siete tablas.</li>
    </ul>
  </div>
</section>

<section>
  <div class="spine">07</div>
  <div class="body-col">
    <h2>Resultados del análisis</h2>
    <h3>Evolución de los saldos del sistema</h3>
    <p>Las captaciones registran una tasa de crecimiento superior a la de las colocaciones durante
    todo el periodo, y la diferencia entre ambas series se amplía de forma sostenida.</p>
    <figure>
      <div class="figbox">{inf.grafico_evolucion()}</div>
      <figcaption><b>Figura 3.</b> Saldos trimestrales del sistema de banca privada, en miles de
      millones de dólares. Cortes de fin de trimestre.</figcaption>
    </figure>
    <h3>Calidad de la cartera</h3>
    <p>El índice de morosidad del sistema se mantiene estable en el periodo ({kpi_mor}). La
    dispersión entre segmentos es amplia: el microcrédito registra un índice seis veces superior
    al del crédito productivo.</p>
    <figure>
      <div class="figbox">{inf.grafico_morosidad()}</div>
      <figcaption><b>Figura 4.</b> Cartera improductiva sobre cartera bruta por segmento de
      crédito, 2026.</figcaption>
    </figure>
    <h3>Concentración del mercado</h3>
    <p>Cuatro entidades concentran el 66,9 % de las captaciones del sistema. La clasificación por
    tamaño no procede de una fuente externa: se deriva de los propios datos mediante un criterio
    de Pareto sobre el volumen acumulado de captaciones, y su metodología queda documentada en
    <code>etl/01_extraccion_fuentes.py</code>.</p>
    <div class="tw"><table>
      <thead><tr><th>Grupo</th><th class="n">Bancos</th><th class="n">Cuota de captaciones</th></tr></thead>
      <tbody>{"".join(f'<tr><td><span class="chip{" warm" if r.g=="GRANDE" else ""}">{r.g.replace("PEQUENO","PEQUEÑO")}</span></td><td class="n">{r.b}</td><td class="n">{es_num(r.p)} %</td></tr>' for _,r in conc.iterrows())}</tbody>
    </table></div>
    <div class="tw"><table>
      <thead><tr><th>Entidad</th><th>Grupo</th><th class="n">Captaciones (millones USD)</th><th class="n">Clientes</th></tr></thead>
      <tbody>{"".join(f'<tr><td><b>{r.e}</b></td><td class="muted">{r.g.replace("PEQUENO","PEQUEÑO")}</td><td class="n">{es_num(r.s)}</td><td class="n">{es_num(r.c)}</td></tr>' for _,r in top.iterrows())}</tbody>
    </table></div>
    <p class="muted" style="font-size:13.5px">Corte de mayo 2026.</p>
  </div>
</section>

<section>
  <div class="spine">08</div>
  <div class="body-col">
    <h2>Conclusiones</h2>
    <ol>
      <li>El flujo integra cuatro tecnologías de origen distintas en un modelo estrella único y
      carga {mil(n_fact)} registros de hechos.</li>
      <li>La configuración de una sola tabla de hechos con dimensión de tipo de operación permite
      comparar el activo y el pasivo de cada entidad en una misma consulta.</li>
      <li>La normalización de nombres y la historificación SCD-2 reducen el recuento de 26 razones
      sociales a 25 entidades con 26 versiones, lo que preserva la continuidad de las series
      históricas.</li>
      <li>La dimensión geográfica se completa con datos de dos fuentes distintas, dado que ninguna
      de ellas contiene la totalidad de los atributos.</li>
      <li>La contenerización de la infraestructura permite reproducir el proceso completo en
      cualquier equipo con Docker.</li>
    </ol>
  </div>
</section>

<footer>
  <span>Universidad San Francisco de Quito · Ingeniería de Datos</span>
  <span>Datos: Superintendencia de Bancos del Ecuador</span>
  <span>Periodo ene 2024 – may 2026</span>
  <span>DW: PostgreSQL 16 · esquema <code class="k">dw</code></span>
</footer>
</div>
"""
# Los SVG heredan blancos fijos del generador del PDF. Se sustituyen por
# tokens de tema, salvo el texto blanco que va sobre relleno de color.
HTML = (HTML
        .replace('fill="#ffffff" stroke=', 'fill="var(--surface)" stroke=')  # cajas
        .replace('stroke="#ffffff"', 'stroke="var(--surface)"')              # anillos
        .replace('fill="#fbf9f6"', 'fill="var(--surface-2)"'))               # caja KNIME
open("/proyecto/informe/artefacto.html", "w", encoding="utf-8").write(HTML)
print("artefacto generado:", len(HTML), "bytes")
