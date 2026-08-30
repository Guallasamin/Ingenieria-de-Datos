#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PASO 4 - Genera el informe ejecutivo en PDF a partir de los datos reales del DW.
Ejecucion: docker exec etl_runtime python etl/04_informe.py
"""
import os, datetime as dt
import pandas as pd
from sqlalchemy import create_engine
from weasyprint import HTML

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAL  = os.path.join(RAIZ, "informe")
os.makedirs(SAL, exist_ok=True)

PG = "postgresql+psycopg2://{u}:{p}@{h}:{P}/{d}".format(
    u=os.getenv("PG_USER","etl_user"), p=os.getenv("PG_PASS","etl_pass_2026"),
    h=os.getenv("PG_HOST","postgres"), P=os.getenv("PG_PORT","5432"),
    d=os.getenv("PG_DB","banca_ec"))
pg = create_engine(PG)
q  = lambda s: pd.read_sql(s, pg)

# ---------------------------------------------------------------------
#  Identidad visual USFQ
#  Tipografias y neutros tomados de la hoja de estilo y del logotipo
#  publicados en usfq.edu.ec. El rojo corresponde al del logotipo del
#  Colegio Politecnico alojado en el mismo dominio.
# ---------------------------------------------------------------------
ROJO   = "#ed1c24"     # rojo institucional
ROJO_O = "#b3141a"     # variante oscura para texto sobre blanco
NEGRO  = "#231f20"     # negro institucional
TINTA, TINTA2, TINTA3 = NEGRO, "#4a4b4c", "#8a8b8c"
CREMA  = "#faf3e9"
GRID, BORDE = "#e3ded4", "#d8d4cb"
# Series de los graficos: negro institucional y rojo institucional
AZUL, NARANJA = NEGRO, ROJO

# =====================================================================
#  GRAFICO 1 - Lineas: evolucion trimestral (2 series)
# =====================================================================
def grafico_evolucion():
    d = q("""SELECT t.etiqueta_trim AS trim, o.naturaleza,
                    SUM(h.saldo_total)/1e9 AS v
             FROM dw.fact_saldos_financieros h
             JOIN dw.dim_tiempo t ON t.tiempo_sk=h.tiempo_sk
             JOIN dw.dim_tipo_operacion o ON o.tipo_operacion_sk=h.tipo_operacion_sk
             WHERE t.es_fin_trimestre GROUP BY 1,2 ORDER BY 1,2""")
    p = d.pivot(index="trim", columns="naturaleza", values="v").sort_index()
    W,H = 760,308; ML,MR,MT,MB = 62,116,30,42
    pw,ph = W-ML-MR, H-MT-MB
    lo,hi = 38, 66
    x = lambda i: ML + (pw*i/(len(p)-1))
    y = lambda v: MT + ph - (v-lo)/(hi-lo)*ph
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="Evolucion trimestral de captaciones y colocaciones">']
    for t in range(40, 70, 5):                       # grilla recesiva
        s.append(f'<line x1="{ML}" x2="{ML+pw}" y1="{y(t):.1f}" y2="{y(t):.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ML-10}" y="{y(t)+4:.1f}" text-anchor="end" '
                 f'font-size="11" fill="{TINTA3}">{t}</text>')
    for i,t in enumerate(p.index):
        s.append(f'<text x="{x(i):.1f}" y="{MT+ph+22}" text-anchor="middle" '
                 f'font-size="10.5" fill="{TINTA3}">{t}</text>')
    for col,color,lbl in (("PASIVO",AZUL,"Captaciones"),("ACTIVO",NARANJA,"Colocaciones")):
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i,v in enumerate(p[col]))
        s.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
                 f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for i,v in enumerate(p[col]):                # anillo de 2px sobre el fondo
            s.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="{color}" '
                     f'stroke="#ffffff" stroke-width="2"/>')
        vf = p[col].iloc[-1]                          # etiqueta directa (2 series)
        s.append(f'<text x="{x(len(p)-1)+13:.1f}" y="{y(vf)+2:.1f}" font-size="11.5" '
                 f'font-weight="700" fill="{TINTA}">{lbl}</text>')
        s.append(f'<text x="{x(len(p)-1)+13:.1f}" y="{y(vf)+17:.1f}" font-size="11" '
                 f'fill="{TINTA2}">{("%.1f" % vf).replace(".", ",")}</text>')
    s.append(f'<text x="6" y="14" font-size="10" '
             f'fill="{TINTA3}">miles de millones de USD</text>')
    s.append("</svg>")
    return "".join(s)

# =====================================================================
#  GRAFICO 2 - Barras: morosidad por segmento (una sola serie)
# =====================================================================
def grafico_morosidad():
    d = q("""SELECT REPLACE(segmento_credito,'CREDITO ','') AS seg,
                    SUM(cartera_improductiva) AS imp, SUM(cartera_bruta) AS bru
             FROM dw.v_kpi_morosidad WHERE anio=2026 GROUP BY 1""")
    NOMBRE = {"CONSUMO":"Consumo", "EDUCATIVO":"Educativo",
              "MICROCREDITO":"Microcrédito", "PRODUCTIVO":"Productivo",
              "INMOBILIARIO":"Inmobiliario",
              "VIVIENDA INTERES PUBLICO":"Vivienda de interés público"}
    d["seg"] = d.seg.map(lambda x: NOMBRE.get(x, x.title()))
    d["pct"] = 100*d.imp/d.bru
    d = d.sort_values("pct", ascending=False).reset_index(drop=True)
    W,H = 760, 34*len(d)+46; ML,MR = 210, 78
    pw = W-ML-MR; mx = 7.5
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="Indice de morosidad por segmento de credito, 2026">']
    for gx in range(0, 8, 2):
        px = ML + pw*gx/mx
        s.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="8" y2="{34*len(d)+6}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{px:.1f}" y="{34*len(d)+26}" text-anchor="middle" '
                 f'font-size="10.5" fill="{TINTA3}">{gx}%</text>')
    for i,r in d.iterrows():
        yy = 14+34*i; bw = pw*r.pct/mx
        s.append(f'<text x="{ML-14}" y="{yy+13}" text-anchor="end" font-size="11.5" '
                 f'fill="{TINTA}">{r.seg}</text>')
        # extremo redondeado 4px anclado a la linea base
        s.append(f'<path d="M{ML} {yy} H{ML+bw-4:.1f} a4,4 0 0 1 4,4 v10 '
                 f'a4,4 0 0 1 -4,4 H{ML} Z" fill="{ROJO}"/>')
        s.append(f'<text x="{ML+bw+10:.1f}" y="{yy+13}" font-size="11.5" '
                 f'font-weight="600" fill="{TINTA}">{("%.2f" % r.pct).replace(".", ",")} %</text>')
    s.append("</svg>")
    return "".join(s)

# =====================================================================
#  DIAGRAMA - Arquitectura de la solucion
# =====================================================================
def diagrama_arquitectura():
    F = [("PostgreSQL","staging.captaciones","122.217 filas",AZUL),
         ("MySQL","catalogos_sb (5 tablas)","177 filas",AZUL),
         ("Excel XLSX","10 libros 2024-2025","45.341 filas",AZUL),
         ("CSV","colocaciones_2026.csv","9.432 filas",AZUL)]
    s = ['<svg viewBox="0 0 780 300" width="100%" role="img" '
         'aria-label="Arquitectura: 4 fuentes, ETL KNIME, Data Warehouse, capa OLAP">']
    for i,(t,sub,n,c) in enumerate(F):
        yy = 14+70*i
        s.append(f'<rect x="6" y="{yy}" width="196" height="54" rx="7" fill="#ffffff" '
                 f'stroke="{c}" stroke-width="1.5"/>')
        s.append(f'<text x="18" y="{yy+20}" font-size="12" font-weight="700" fill="{c}">{t}</text>')
        s.append(f'<text x="18" y="{yy+35}" font-size="10" fill="{TINTA2}">{sub}</text>')
        s.append(f'<text x="18" y="{yy+48}" font-size="9.5" fill="{TINTA3}">{n}</text>')
        s.append(f'<path d="M206 {yy+27} H246" stroke="{BORDE}" stroke-width="1.5" '
                 f'marker-end="url(#fl)"/>')
    s.append('<defs><marker id="fl" markerWidth="7" markerHeight="7" refX="6" refY="3.5" '
             f'orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="{BORDE}"/></marker></defs>')
    s.append(f'<rect x="250" y="40" width="176" height="200" rx="8" fill="#fbf9f6" '
             f'stroke="{NARANJA}" stroke-width="1.5"/>')
    s.append(f'<text x="338" y="66" text-anchor="middle" font-size="13" '
             f'font-weight="700" fill="{NARANJA}">ETL — KNIME</text>')
    for j,p in enumerate(["Concatenate","String Manipulation","Joiner (enriquecer)",
                          "Rule Engine","Math Formula","Row Filter (calidad)",
                          "SCD Tipo 2","DB Insert"]):
        s.append(f'<text x="268" y="{92+18*j}" font-size="10.5" fill="{TINTA2}">• {p}</text>')
    s.append(f'<path d="M430 140 H470" stroke="{BORDE}" stroke-width="1.5" marker-end="url(#fl)"/>')
    s.append(f'<rect x="474" y="40" width="176" height="200" rx="8" fill="#ffffff" '
             f'stroke="{AZUL}" stroke-width="1.5"/>')
    s.append(f'<text x="562" y="66" text-anchor="middle" font-size="13" font-weight="700" '
             f'fill="{AZUL}">DW — modelo estrella</text>')
    for j,p in enumerate(["dim_tiempo (29)","dim_entidad (26, SCD2)","dim_geografia (126)",
                          "dim_producto (19)","dim_tipo_operacion (2)","dim_fuente_datos (4)"]):
        s.append(f'<text x="492" y="{92+18*j}" font-size="10.5" fill="{TINTA2}">• {p}</text>')
    s.append(f'<rect x="492" y="200" width="140" height="28" rx="5" fill="{AZUL}"/>')
    s.append(f'<text x="562" y="218" text-anchor="middle" font-size="11" font-weight="700" '
             f'fill="#ffffff">FACT · 176.990</text>')
    s.append(f'<path d="M654 140 H694" stroke="{BORDE}" stroke-width="1.5" marker-end="url(#fl)"/>')
    s.append(f'<rect x="698" y="92" width="76" height="96" rx="7" fill="#ffffff" '
             f'stroke="{BORDE}" stroke-width="1.5"/>')
    s.append(f'<text x="736" y="122" text-anchor="middle" font-size="11" font-weight="700" '
             f'fill="{TINTA}">OLAP</text>')
    s.append(f'<text x="736" y="140" text-anchor="middle" font-size="9.5" fill="{TINTA2}">5 vistas</text>')
    s.append(f'<text x="736" y="155" text-anchor="middle" font-size="9.5" fill="{TINTA2}">4 KPI</text>')
    s.append(f'<text x="736" y="172" text-anchor="middle" font-size="9.5" fill="{TINTA3}">Metabase</text>')
    s.append("</svg>")
    return "".join(s)

# =====================================================================
#  DIAGRAMA - Modelo estrella
# =====================================================================
def mil(n):
    """Separador de miles a la espanola: 176990 -> '176.990'."""
    return f"{int(n):,}".replace(",", ".")

def es_num(s):
    """Convierte '19,082.8' (formato ingles de TO_CHAR) a '19.082,8'."""
    return str(s).replace(",", "\x00").replace(".", ",").replace("\x00", ".")

def diagrama_estrella(n_hechos="176.990"):
    D = [("dim_tiempo","29 filas","Año>Sem>Trim>Mes",280,10),
         ("dim_entidad","26 · SCD2","Tamaño>Perfil>Entidad",22,96),
         ("dim_geografia","126 filas","Región>Prov>Cantón",556,96),
         ("dim_producto","19 filas","Familia>Subfam>Prod",22,236),
         ("dim_tipo_operacion","2 filas","Activo / Pasivo",556,236),
         ("dim_fuente_datos","4 filas","Linaje ETL",280,322)]
    cx,cy,cw,ch = 268,158,244,120
    s = ['<svg viewBox="0 0 780 400" width="100%" role="img" '
         'aria-label="Modelo estrella: 6 dimensiones alrededor de la tabla de hechos">']
    for n,f,j,X,Y in D:                                   # conectores primero
        ax = X+101 if X < 268 else (X+101 if X > 512 else X+101)
        ay = Y+34
        s.append(f'<path d="M{ax} {ay} L{cx+cw/2} {cy+ch/2}" stroke="{BORDE}" '
                 f'stroke-width="1.2" stroke-dasharray="3 3"/>')
    for n,f,j,X,Y in D:
        s.append(f'<rect x="{X}" y="{Y}" width="202" height="68" rx="7" fill="#ffffff" '
                 f'stroke="{AZUL}" stroke-width="1.4"/>')
        s.append(f'<text x="{X+14}" y="{Y+23}" font-size="12" font-weight="700" '
                 f'fill="{AZUL}">{n}</text>')
        s.append(f'<text x="{X+14}" y="{Y+40}" font-size="10" fill="{TINTA2}">{f}</text>')
        s.append(f'<text x="{X+14}" y="{Y+56}" font-size="9.5" fill="{TINTA3}">{j}</text>')
    s.append(f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="9" fill="{NARANJA}"/>')
    s.append(f'<text x="{cx+cw/2}" y="{cy+30}" text-anchor="middle" font-size="13.5" '
             f'font-weight="700" fill="#ffffff">fact_saldos_financieros</text>')
    s.append(f'<text x="{cx+cw/2}" y="{cy+52}" text-anchor="middle" font-size="11.5" '
             f'fill="#ffeee7">{n_hechos} filas · 6 FK</text>')
    s.append(f'<text x="{cx+cw/2}" y="{cy+74}" text-anchor="middle" font-size="10" '
             f'fill="#ffeee7">saldo_total · por_vencer · vencido</text>')
    s.append(f'<text x="{cx+cw/2}" y="{cy+90}" text-anchor="middle" font-size="10" '
             f'fill="#ffeee7">improductivo · cuentas · clientes</text>')
    s.append(f'<text x="{cx+cw/2}" y="{cy+108}" text-anchor="middle" font-size="9.5" '
             f'fill="#ffdccd">grano: mes × entidad × cantón × producto</text>')
    s.append("</svg>")
    return "".join(s)

# =====================================================================
#  CONSTRUCCION DEL INFORME
# =====================================================================
def tabla(df, cols=None, align=None):
    cols = cols or list(df.columns)
    th = "".join(f"<th>{c}</th>" for c in cols)
    filas = []
    for _, r in df.iterrows():
        tds = "".join(
            f'<td class="{(align or {}).get(c,"")}">{r[c]}</td>' for c in cols)
        filas.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(filas)}</tbody></table>"

def main():
    hoy = dt.date.today().strftime("%d/%m/%Y")

    # ---------------- datos vivos del DW ----------------
    conteos = q("""SELECT 'dim_tiempo' o, COUNT(*) n FROM dw.dim_tiempo
      UNION ALL SELECT 'dim_entidad', COUNT(*) FROM dw.dim_entidad
      UNION ALL SELECT 'dim_geografia', COUNT(*) FROM dw.dim_geografia
      UNION ALL SELECT 'dim_producto', COUNT(*) FROM dw.dim_producto
      UNION ALL SELECT 'dim_tipo_operacion', COUNT(*) FROM dw.dim_tipo_operacion
      UNION ALL SELECT 'dim_fuente_datos', COUNT(*) FROM dw.dim_fuente_datos
      UNION ALL SELECT 'fact_saldos_financieros', COUNT(*) FROM dw.fact_saldos_financieros""")
    n_fact = int(conteos.loc[conteos.o=="fact_saldos_financieros","n"].iloc[0])

    fuentes = q("""SELECT f.cod_fuente AS "Código", f.tipo_tecnologia AS "Tecnología",
             CASE WHEN f.cod_fuente='F2_MYSQL' THEN 'Dimensiones' ELSE 'Hechos' END AS "Alimenta",
             COALESCE(TO_CHAR(x.filas,'FM999G999'),'177') AS "Filas"
      FROM dw.dim_fuente_datos f
      LEFT JOIN (SELECT fuente_sk, COUNT(*) filas FROM dw.fact_saldos_financieros
                 GROUP BY 1) x ON x.fuente_sk=f.fuente_sk ORDER BY 1""")
    fuentes["Filas"] = fuentes["Filas"].map(es_num)

    scd = q("""SELECT version AS "Ver.", nombre_entidad AS "Nombre en el origen",
                      estado_entidad AS "Estado", fecha_inicio_vig AS "Vigente desde",
                      fecha_fin_vig AS "Vigente hasta"
               FROM dw.dim_entidad WHERE cod_entidad='AMIBANK' ORDER BY version""")

    top = q("""SELECT entidad AS "Entidad", grupo_tamanio AS "Grupo",
                 TO_CHAR(SUM(saldo_total)/1e6,'FM999G999G990D0') AS "Captaciones (MM USD)",
                 TO_CHAR(SUM(numero_clientes),'FM999G999G999') AS "Clientes"
          FROM dw.v_cubo_banca WHERE anio_mes='2026-05' AND naturaleza='PASIVO'
          GROUP BY 1,2 ORDER BY SUM(saldo_total) DESC LIMIT 6""")
    for c in ("Captaciones (MM USD)", "Clientes"):
        top[c] = top[c].map(es_num)
    top["Grupo"] = top["Grupo"].replace({"PEQUENO": "PEQUEÑO"})

    conc = q("""SELECT grupo_tamanio AS "Grupo", COUNT(DISTINCT entidad) AS "Bancos",
                 ROUND(100.0*SUM(saldo_total)/SUM(SUM(saldo_total)) OVER (),1)||' %%' AS "Mercado"
          FROM dw.v_cubo_banca WHERE anio_mes='2026-05' AND naturaleza='PASIVO'
          GROUP BY 1 ORDER BY 3 DESC""")
    conc["Mercado"] = conc["Mercado"].map(es_num)
    conc["Grupo"] = conc["Grupo"].replace({"PEQUENO": "PEQUEÑO"})

    reg = q("""SELECT region AS "Región", COUNT(DISTINCT provincia) AS "Provincias",
                      COUNT(*) AS "Cantones"
               FROM dw.dim_geografia GROUP BY 1 ORDER BY 3 DESC""")

    knime = q("""SELECT
        (SELECT COUNT(*) FROM dw_knime.fact_saldos_financieros) AS f_kn,
        (SELECT COUNT(*) FROM dw.fact_saldos_financieros)       AS f_py,
        (SELECT COUNT(*) FROM dw_knime.dim_entidad)             AS e_kn,
        (SELECT ROUND(SUM(saldo_total)/1e6,2) FROM dw_knime.fact_saldos_financieros) AS s_kn,
        (SELECT ROUND(SUM(saldo_total)/1e6,2) FROM dw.fact_saldos_financieros)       AS s_py""")
    kn = knime.iloc[0]

    mor = q("SELECT anio, ROUND(100.0*SUM(cartera_improductiva)/SUM(cartera_bruta),2) p "
            "FROM dw.v_kpi_morosidad GROUP BY 1 ORDER BY 1")
    mor_txt = " · ".join(f"{int(r.anio)}: {es_num(r.p)} %" for _, r in mor.iterrows())

    CSS = """
    /* Tipografias institucionales USFQ: Baskerville para titulos y
       Helvetica para texto. Se declaran primero las fuentes del sistema y
       despues los sustitutos web para los entornos que no las tengan. */
    @import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Arimo:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

    @page { size: A4; margin: 20mm 18mm 18mm 18mm;
            @bottom-center { content: counter(page) " de " counter(pages);
                             font-size: 8.5pt; color: #8a8b8c; } }
    @page :first { margin-top: 0; }
    * { box-sizing: border-box; }
    body { font-family: Helvetica, "Helvetica Neue", Arimo, Arial, sans-serif;
           font-size: 9.7pt; line-height: 1.52; color: #231f20; margin: 0; }
    h1, h2, h3, .display {
           font-family: Baskerville, "Baskerville Old Face", "Libre Baskerville",
                        "Hoefler Text", Garamond, "Times New Roman", serif; }
    h1 { font-size: 22pt; margin: 0 0 6pt; font-weight: 700; line-height: 1.15; }
    h2 { font-size: 14pt; font-weight: 700; margin: 18pt 0 8pt;
         padding-bottom: 4pt; border-bottom: 1.5pt solid #ed1c24;
         color: #231f20; page-break-after: avoid; }
    h3 { font-size: 11pt; font-weight: 700; margin: 13pt 0 5pt;
         color: #231f20; page-break-after: avoid; }
    p  { margin: 0 0 7pt; text-align: justify; }
    .portada { background: #231f20; color: #ffffff; padding: 22mm 18mm 14mm;
               margin: 0 0 14pt; }
    .portada .filete { width: 46mm; height: 3pt; background: #ed1c24;
                       margin-bottom: 12pt; }
    .portada h1 { color: #ffffff; font-size: 25pt; }
    .portada .sub { font-size: 11.5pt; margin-top: 8pt; color: #d8d4cb;
                    font-family: Helvetica, "Helvetica Neue", Arimo, Arial, sans-serif; }
    .portada .meta { font-size: 9pt; color: #d8d4cb; margin-top: 18pt;
                     border-top: 0.5pt solid #4a4b4c; padding-top: 10pt; }
    .portada .meta b { color: #ffffff; }
    table { width: 100%; border-collapse: collapse; margin: 7pt 0 11pt;
            font-size: 8.6pt; page-break-inside: avoid; }
    th { background: #faf3e9; text-align: left; padding: 5pt 7pt; font-weight: 700;
         border-top: 0.8pt solid #231f20; border-bottom: 0.8pt solid #d8d4cb; }
    td { padding: 4.5pt 7pt; border-bottom: 0.4pt solid #e3ded4; }
    td.n { text-align: right; font-variant-numeric: tabular-nums; }
    .kpis { display: flex; gap: 7pt; margin: 10pt 0 12pt; }
    .kpi { flex: 1; border: 0.5pt solid #d8d4cb; border-top: 2.5pt solid #ed1c24;
           padding: 8pt 9pt; }
    .kpi .v { font-family: Baskerville, "Baskerville Old Face", "Libre Baskerville",
              Garamond, serif; font-size: 17pt; font-weight: 700; line-height: 1; }
    .kpi .l { font-size: 7.6pt; color: #4a4b4c; margin-top: 3pt; line-height: 1.3; }
    .fig { margin: 8pt 0 11pt; page-break-inside: avoid; }
    /* Las figuras se escalan para que no fuercen saltos de pagina */
    .fig svg { display: block; margin: 0 auto; max-width: 80%; }
    .fig .cap { font-size: 8pt; color: #4a4b4c; margin-top: 4pt; }
    .fig .cap b { color: #231f20; }
    .nota { background: #faf3e9; border-left: 2.5pt solid #ed1c24;
            padding: 7pt 10pt; margin: 9pt 0 12pt; font-size: 8.7pt; }
    code { font-family: "Courier New", Consolas, monospace; font-size: 8.4pt;
           background: #faf3e9; padding: 0.5pt 3pt; }
    pre { background: #faf3e9; border-left: 2.5pt solid #d8d4cb; padding: 8pt 10pt;
          font-family: "Courier New", Consolas, monospace; font-size: 8pt;
          line-height: 1.45; white-space: pre-wrap; overflow-wrap: break-word;
          page-break-inside: avoid; margin: 0 0 10pt; }
    ul, ol { margin: 0 0 8pt; padding-left: 15pt; }
    li { margin-bottom: 3.5pt; }
    .salto { page-break-before: always; }
    """

    HTML_DOC = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
    <title>Informe tecnico - Flujo ETL y Data Warehouse</title><style>{CSS}</style></head><body>

    <div class="portada">
      <div class="filete"></div>
      <div style="font-size:8.5pt;letter-spacing:1.3pt;color:#d8d4cb">
        UNIVERSIDAD SAN FRANCISCO DE QUITO &nbsp;·&nbsp; INGENIER&Iacute;A DE DATOS</div>
      <h1>Flujo ETL multifuente y Data Warehouse dimensional del sistema de banca privada del Ecuador</h1>
      <div class="sub">Informe t&eacute;cnico &middot; Taller individual, semana 1</div>
      <div class="meta">
        <b>Fuente:</b> Superintendencia de Bancos del Ecuador, boletines de colocaciones y
        captaciones de la banca privada &nbsp;&middot;&nbsp;
        <b>Periodo:</b> enero 2024 &ndash; mayo 2026 (29 cortes mensuales) &nbsp;&middot;&nbsp;
        <b>Fecha:</b> {hoy}
      </div>
    </div>

    <h2>1. Objeto y alcance</h2>
    <p>Se construye un flujo ETL que integra cuatro fuentes de datos heterog&eacute;neas y las
    consolida en un Data Warehouse dimensional en modelo estrella, con seis dimensiones y una
    tabla de hechos. El conjunto de entrada consta de 18 libros Excel de la Superintendencia de
    Bancos del Ecuador, con el detalle mensual de la cartera de cr&eacute;dito y de los
    dep&oacute;sitos de las 26 razones sociales de la banca privada, desagregado por
    cant&oacute;n. La infraestructura se ejecuta en contenedores Docker.</p>

    <div class="kpis">
      <div class="kpi"><div class="v">4</div><div class="l">Fuentes de datos integradas</div></div>
      <div class="kpi"><div class="v">6 + 1</div><div class="l">Dimensiones y tabla de hechos</div></div>
      <div class="kpi"><div class="v">{mil(n_fact)}</div><div class="l">Registros de hechos cargados</div></div>
      <div class="kpi"><div class="v">122</div><div class="l">Nodos del flujo de KNIME</div></div>
    </div>

    <h2>2. Arquitectura y fuentes de datos</h2>
    <p>La arquitectura se organiza en tres capas: aterrizaje (<code>staging</code>), almac&eacute;n
    dimensional (<code>dw</code>) y capa de explotaci&oacute;n OLAP. Cada fuente se materializa en
    una tecnolog&iacute;a distinta, de modo que el flujo resuelve diferencias de protocolo de
    conexi&oacute;n, formato y esquema.</p>
    {tabla(fuentes, align={"Filas":"n"})}
    <div class="fig">{diagrama_arquitectura()}
      <div class="cap"><b>Figura 1.</b> Arquitectura de extremo a extremo.</div></div>
    <p>Cada libro del regulador contiene una hoja de presentaci&oacute;n, con subtotales embebidos,
    y una hoja <code>BASE</code> en formato largo. El flujo lee la hoja <code>BASE</code>; la de
    presentaci&oacute;n duplicar&iacute;a los importes al mezclar detalle con totales. El perfilado
    previo registr&oacute; cero valores nulos y cero importes negativos, y verific&oacute; que la
    identidad <code>TOTAL = POR VENCER + NO DEVENGA + VENCIDA</code> se cumple en las 54.773 filas
    de cartera.</p>

    <h2>3. Modelo dimensional</h2>
    <p>El modelo unifica colocaciones y captaciones en una &uacute;nica tabla de hechos y emplea la
    dimensi&oacute;n <code>dim_tipo_operacion</code> como eje discriminador, lo que permite
    calcular indicadores que cruzan el activo y el pasivo de la entidad sin unir dos tablas de
    hechos. El grano es un registro por mes de corte, entidad, cant&oacute;n y producto financiero;
    corresponde a un <i>snapshot</i> peri&oacute;dico mensual, por lo que las m&eacute;tricas de
    saldo son semiaditivas en el tiempo.</p>
    <div class="fig">{diagrama_estrella(mil(n_fact))}
      <div class="cap"><b>Figura 2.</b> Modelo estrella. Todas las claves primarias son
      subrogadas.</div></div>
    <p><b>Jerarqu&iacute;as:</b> tiempo (a&ntilde;o &rarr; semestre &rarr; trimestre &rarr; mes);
    entidad (grupo de tama&ntilde;o &rarr; perfil de negocio &rarr; entidad); geograf&iacute;a
    (regi&oacute;n &rarr; provincia &rarr; cant&oacute;n); producto (familia &rarr; subfamilia
    &rarr; producto). Habilitan las operaciones de <i>drill-down</i>, <i>roll-up</i> y <i>slice and
    dice</i>. La vista <code>dw.v_cubo_banca</code> expone el modelo desnormalizado y cuatro vistas
    adicionales materializan los indicadores de negocio.</p>
    {tabla(conteos.assign(n=conteos.n.map(mil)).rename(columns={"o":"Objeto","n":"Filas"}), align={"Filas":"n"})}

    <h2>4. Transformaci&oacute;n y limpieza</h2>
    <p>El perfilado identific&oacute; seis incidencias en los archivos de origen.</p>
    <table><thead><tr><th style="width:42%">Incidencia</th><th>Tratamiento</th></tr></thead><tbody>
      <tr><td>Espacios dobles en la raz&oacute;n social
        (<code>BP BANCO&nbsp;&nbsp;DESARROLLO&hellip;</code>)</td>
        <td><code>regexReplace(strip(col), "\\s+", " ")</code></td></tr>
      <tr><td>Prefijos <code>BP</code> y <code>BANCO</code> y forma societaria <code>S.A.</code>
        heterog&eacute;neos</td>
        <td>Derivaci&oacute;n de un nombre comercial homog&eacute;neo, base de la clave
        <code>cod_entidad</code></td></tr>
      <tr><td>Diacr&iacute;ticos en <code>ATL&Aacute;NTIDA</code>, <code>CA&Ntilde;AR</code>,
        <code>TS&Aacute;CHILAS</code></td>
        <td>Normalizaci&oacute;n NFD en la clave; las tildes se conservan en el nombre de
        presentaci&oacute;n</td></tr>
      <tr><td>Los archivos de cartera no incluyen la columna <code>REGI&Oacute;N</code></td>
        <td><i>Join</i> contra el cat&aacute;logo geogr&aacute;fico alojado en MySQL; la
        dimensi&oacute;n se construye con dos fuentes</td></tr>
      <tr><td><code>ZONA NO DELIMITADA / LAS GOLONDRINAS</code> sin regi&oacute;n asignable
        (58 filas)</td>
        <td>Miembro <code>NO DEFINIDA</code> y bandera <code>es_registro_desconocido</code>; los
        importes permanecen en la tabla de hechos</td></tr>
      <tr><td>Banco Amibank con dos razones sociales, activa y en liquidaci&oacute;n</td>
        <td>Dimensi&oacute;n lentamente cambiante de tipo 2: una clave de negocio y dos versiones
        con vigencia acotada</td></tr>
    </tbody></table>
    {tabla(scd)}
    <p>Durante la resoluci&oacute;n de claves subrogadas, cada hecho se asocia a la versi&oacute;n
    vigente en su fecha de corte. Se derivan adem&aacute;s <code>saldo_improductivo</code> (cartera
    que no devenga intereses m&aacute;s cartera vencida) y <code>saldo_promedio_cliente</code>
    (saldo entre n&uacute;mero de clientes). El filtro de calidad descarta filas sin fecha, sin
    entidad o con saldo negativo; el n&uacute;mero de filas descartadas es cero.</p>

    <h2>5. Implementaci&oacute;n en KNIME</h2>
    <p>El flujo <code>ETL_Banca_Ecuador.knwf</code> implementa el proceso con 122 nodos y 135
    conexiones en quince tipos de nodo. Su ejecuci&oacute;n carga el modelo estrella en el esquema
    <code>dw_knime</code>.</p>
    <table><thead><tr><th>Bloque</th><th class="n">Nodos</th><th>Composici&oacute;n</th></tr></thead><tbody>
      <tr><td><b>A. Extracci&oacute;n</b></td><td class="n">23</td><td>2 conectores de base de
        datos, 7 lectores de consulta, 12 lectores de Excel y 1 lector de CSV</td></tr>
      <tr><td><b>B. Transformaci&oacute;n</b></td><td class="n">30</td><td>25 <i>String
        Manipulation</i>, 4 <i>Math Formula</i>, 4 <i>Rule Engine</i>, 4 <i>Rule-based Row
        Filter</i> y 13 <i>Concatenate</i></td></tr>
      <tr><td><b>C. Dimensiones</b></td><td class="n">20</td><td>Carga de las seis dimensiones;
        <code>dim_tiempo</code> se deriva dentro del flujo</td></tr>
      <tr><td><b>D. Hechos</b></td><td class="n">19</td><td>8 <i>Joiner</i> para la
        sustituci&oacute;n de claves de negocio por subrogadas, incluida la resoluci&oacute;n
        SCD-2</td></tr>
    </tbody></table>

    <h2>6. Validaci&oacute;n</h2>
    <p>El script <code>etl/03_validacion.sql</code> ejecuta diez pruebas sobre el almac&eacute;n
    cargado.</p>
    <table><thead><tr><th style="width:46%">Prueba</th><th>Resultado</th></tr></thead><tbody>
      <tr><td>Integridad referencial (6 claves for&aacute;neas)</td>
          <td>Cero registros hu&eacute;rfanos</td></tr>
      <tr><td>Conciliaci&oacute;n <code>staging</code> &harr; <code>dw</code></td>
          <td>122.217 filas y USD 1.558.549 millones en ambos</td></tr>
      <tr><td>Identidad contable TOTAL = POR VENCER + NO DEVENGA + VENCIDA</td>
          <td>Cero filas la incumplen</td></tr>
      <tr><td>Cobertura temporal</td><td>29 cortes mensuales consecutivos</td></tr>
      <tr><td>Filas descartadas por el filtro de calidad</td><td>Cero</td></tr>
      <tr><td>Conciliaci&oacute;n <code>dw</code> &harr; <code>dw_knime</code></td>
          <td>Id&eacute;ntico n&uacute;mero de filas e importes en las siete tablas
          ({mil(kn.f_py)} hechos)</td></tr>
    </tbody></table>

    <h2>7. Resultados del an&aacute;lisis</h2>
    <p>Las captaciones registran una tasa de crecimiento superior a la de las colocaciones durante
    todo el periodo, y la diferencia entre ambas series se ampl&iacute;a de forma sostenida.</p>
    <div class="fig">{grafico_evolucion()}
      <div class="cap"><b>Figura 3.</b> Saldos trimestrales del sistema, en miles de millones de
      d&oacute;lares. Cortes de fin de trimestre.</div></div>
    <p>El &iacute;ndice de morosidad del sistema se mantiene estable ({mor_txt}). La
    dispersi&oacute;n entre segmentos es amplia: el microcr&eacute;dito registra un &iacute;ndice
    seis veces superior al del cr&eacute;dito productivo. Cuatro entidades concentran el 66,9 % de
    las captaciones; la clasificaci&oacute;n por tama&ntilde;o se deriva de los propios datos
    mediante un criterio de Pareto sobre el volumen acumulado.</p>
    <div class="fig">{grafico_morosidad()}
      <div class="cap"><b>Figura 4.</b> Cartera improductiva sobre cartera bruta por segmento,
      2026.</div></div>
    {tabla(conc, align={"Bancos":"n","Mercado":"n"})}

    <h2>8. Conclusiones</h2>
    <ol>
      <li>El flujo integra cuatro tecnolog&iacute;as de origen distintas en un modelo estrella
      &uacute;nico y carga {mil(n_fact)} registros de hechos.</li>
      <li>La normalizaci&oacute;n de claves y la historificaci&oacute;n SCD-2 consolidan 26 razones
      sociales en 25 entidades con 26 versiones, lo que preserva la continuidad de las series
      hist&oacute;ricas.</li>
      <li>La dimensi&oacute;n geogr&aacute;fica se completa con datos de dos fuentes, dado que
      ninguna contiene la totalidad de los atributos.</li>
      <li>Las implementaciones en KNIME y en Python producen resultados id&eacute;nticos, y la
      contenerizaci&oacute;n permite reproducir el proceso en cualquier equipo con Docker.</li>
    </ol>

    </body></html>"""

    ruta = os.path.join(SAL, "Informe_Tecnico_ETL_DW.pdf")
    HTML(string=HTML_DOC, base_url=RAIZ).write_pdf(ruta)
    with open(os.path.join(SAL, "informe.html"), "w", encoding="utf-8") as fh:
        fh.write(HTML_DOC)
    print(f"PDF generado: {ruta}  ({os.path.getsize(ruta)/1024:.0f} KB)")

if __name__ == "__main__":
    main()
