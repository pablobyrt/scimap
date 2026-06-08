"""
Scimap — Dashboard bibliométrico interactivo
Uso local:  python app.py [archivo.bib ...]
Deploy:     gunicorn app:server
"""
import sys
import os
import time
import base64
import tempfile
from pathlib import Path

import pandas as pd
import numpy as np

import dash
from dash import dcc, html, Input, Output, State, callback, dash_table, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px

import parser as bp
import analysis as an
import gender_engine as ge
import openalex as oa

# ── datos globales ────────────────────────────────────────────────────────────

DF_FULL   = pd.DataFrame()
DF_GENDER = pd.DataFrame()

# Cargar desde argumento CLI si existe (modo local)
if len(sys.argv) > 1:
    try:
        paths = [Path(p) for p in sys.argv[1:]]
        DF_FULL = bp.load_data(*paths)
        DF_FULL["year"] = pd.to_numeric(DF_FULL["year"], errors="coerce")
        print(f"Cargados {len(DF_FULL)} papers desde archivo.")
        DF_GENDER = ge.gender_analysis_df(DF_FULL, use_genderize=False, use_web=False)
    except Exception as e:
        print(f"Error cargando archivo: {e}")

# ── paleta ────────────────────────────────────────────────────────────────────

BLUE   = "#2563EB"
GREEN  = "#10B981"
AMBER  = "#F59E0B"
RED    = "#EF4444"
PURPLE = "#8B5CF6"
PINK   = "#EC4899"
GRAY   = "#94A3B8"
BG     = "white"
PALETTE = px.colors.qualitative.Plotly


def _fig_layout(fig, height=360):
    fig.update_layout(
        plot_bgcolor=BG, paper_bgcolor=BG,
        margin=dict(t=40, b=30, l=10, r=10),
        height=height,
        font=dict(family="Segoe UI, system-ui, sans-serif", size=12),
    )
    return fig


def _empty_fig(msg="Carga datos para ver este gráfico"):
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=14, color=GRAY))
    fig.update_layout(plot_bgcolor="#F8FAFC", paper_bgcolor=BG,
                      height=360, margin=dict(t=40, b=30, l=10, r=10))
    return fig


def filter_df(years, types, sources, click_filters=None):
    """Filtra DataFrame por años, tipos, fuentes y clicks interactivos."""
    df = DF_FULL.copy()
    if df.empty:
        return df

    # Filtros de rango (slider)
    if years and "year" in df.columns:
        df = df[df["year"].between(years[0], years[1])]
    if types and "type" in df.columns:
        df = df[df["type"].isin(types)]
    if sources and "source" in df.columns:
        df = df[df["source"].isin(sources)]

    # Filtros de click (interactivos)
    if click_filters:
        if click_filters.get("author") and "authors" in df.columns:
            df = df[df["authors"].apply(lambda x: click_filters["author"] in (x if isinstance(x, list) else []))]

        if click_filters.get("institution") and "affiliations" in df.columns:
            df = df[df["affiliations"].str.contains(click_filters["institution"], case=False, na=False)]

        if click_filters.get("year") and "year" in df.columns:
            df = df[df["year"] == click_filters["year"]]

        if click_filters.get("country") and "countries" in df.columns:
            df = df[df["countries"].apply(lambda x: click_filters["country"] in (x if isinstance(x, list) else []))]

    return df


# ── componentes UI ────────────────────────────────────────────────────────────

def stat_card(id_val, label, color=BLUE, icon="📊"):
    return dbc.Card([
        dbc.CardBody([
            html.Div(icon, style={"fontSize": "1.4rem", "marginBottom": "4px"}),
            html.Div(id=id_val, style={
                "fontSize": "2rem", "fontWeight": "700", "color": color, "lineHeight": "1"
            }),
            html.Div(label, style={
                "fontSize": "0.72rem", "color": "#64748b", "textTransform": "uppercase",
                "letterSpacing": "0.05em", "marginTop": "4px",
            }),
        ])
    ], style={"borderTop": f"3px solid {color}", "borderRadius": "10px"})


def section_header(title):
    return html.Div([
        html.Hr(style={"borderColor": "#E2E8F0", "flex": "1", "marginRight": "12px"}),
        html.Span(title, style={
            "fontSize": "0.72rem", "fontWeight": "700", "color": "#64748b",
            "textTransform": "uppercase", "letterSpacing": "0.1em", "whiteSpace": "nowrap",
        }),
        html.Hr(style={"borderColor": "#E2E8F0", "flex": "1", "marginLeft": "12px"}),
    ], style={"display": "flex", "alignItems": "center", "margin": "24px 0 12px"})


def card(children, id_anchor=""):
    props = {"id": id_anchor} if id_anchor else {}
    return dbc.Card(dbc.CardBody(children), style={
        "borderRadius": "12px", "boxShadow": "0 1px 4px rgba(0,0,0,.07)",
        "marginBottom": "16px", **props
    })


# ── sidebar ───────────────────────────────────────────────────────────────────

SIDEBAR = html.Div([

    # Logo
    html.Div([
        html.H4("Scimap", style={"color": "white", "fontWeight": "700", "marginBottom": "0"}),
        html.Small("Bibliometría científica", style={"color": "#94A3B8", "fontSize": "0.75rem"}),
    ], style={"padding": "1.2rem 1.2rem 0.8rem", "borderBottom": "1px solid #334155"}),

    # Upload archivo
    html.Div([
        html.Small("SUBIR ARCHIVO", style={
            "color": "#94A3B8", "fontSize": "0.68rem", "fontWeight": "700",
            "letterSpacing": "0.08em", "display": "block", "marginBottom": "8px",
        }),
        dcc.Upload(
            id="upload-data",
            children=html.Div([
                html.Span("Arrastra tu archivo", style={"fontSize": "0.78rem", "color": "#CBD5E1"}),
                html.Br(),
                html.Span(".bib .txt .xlsx .xls", style={"fontSize": "0.7rem", "color": "#64748B"}),
            ]),
            style={
                "width": "100%", "border": "2px dashed #475569", "borderRadius": "6px",
                "textAlign": "center", "padding": "10px", "cursor": "pointer",
                "background": "#1e293b",
            },
            multiple=False,
        ),
        html.Div(id="upload-status", style={"color": "#10B981", "fontSize": "0.72rem",
                                             "marginTop": "5px", "minHeight": "16px"}),
        html.Hr(style={"borderColor": "#334155", "margin": "10px 0"}),
    ], style={"padding": "0.8rem 1rem 0"}),

    # OpenAlex búsqueda
    html.Div([
        html.Small("OPENALEX — SIN ARCHIVO", style={
            "color": "#94A3B8", "fontSize": "0.68rem", "fontWeight": "700",
            "letterSpacing": "0.08em", "display": "block", "marginBottom": "8px",
        }),
        dcc.Input(id="oa-institution", type="text", debounce=True,
                  placeholder="Institución (ej: U. de Chile)...",
                  style={"width": "100%", "fontSize": "0.78rem", "padding": "4px 8px",
                         "borderRadius": "4px", "border": "1px solid #475569",
                         "background": "#334155", "color": "white", "marginBottom": "4px"}),
        html.Div(id="oa-inst-results", style={"marginBottom": "4px"}),
        dcc.Input(id="oa-keywords", type="text",
                  placeholder="Tema (ej: machine learning, IA)...",
                  style={"width": "100%", "fontSize": "0.78rem", "padding": "4px 8px",
                         "borderRadius": "4px", "border": "1px solid #475569",
                         "background": "#334155", "color": "white", "marginBottom": "6px"}),
        dcc.RangeSlider(id="oa-years", min=2018, max=2026, value=[2022, 2025],
                        marks={y: {"label": str(y), "style": {"color": "#94A3B8", "fontSize": "0.62rem"}}
                               for y in range(2018, 2027, 2)},
                        tooltip={"placement": "bottom"}),
        dbc.Button("Buscar en OpenAlex", id="btn-oa-search", color="success",
                   size="sm", className="mt-2 w-100"),
        html.Div(id="oa-status", style={"color": "#10B981", "fontSize": "0.72rem",
                                         "marginTop": "5px", "minHeight": "16px"}),
        dcc.Store(id="oa-inst-id"),
        html.Hr(style={"borderColor": "#334155", "margin": "10px 0"}),
    ], style={"padding": "0 1rem"}),

    # Filtros globales
    html.Div([
        html.Small("FILTROS", style={
            "color": "#94A3B8", "fontSize": "0.68rem", "fontWeight": "700",
            "letterSpacing": "0.08em", "display": "block", "marginBottom": "8px",
        }),
        html.Label("Años", style={"color": "#CBD5E1", "fontSize": "0.78rem"}),
        dcc.RangeSlider(id="filter-year", min=2018, max=2026, value=[2018, 2026],
                        marks={y: {"label": str(y), "style": {"color": "#94A3B8", "fontSize": "0.62rem"}}
                               for y in range(2018, 2027, 2)},
                        tooltip={"placement": "bottom"}),
        html.Label("Tipo doc.", style={"color": "#CBD5E1", "fontSize": "0.78rem", "marginTop": "8px"}),
        dcc.Dropdown(id="filter-type", multi=True, placeholder="Todos",
                     style={"fontSize": "0.78rem"}),
        html.Label("Fuente", style={"color": "#CBD5E1", "fontSize": "0.78rem", "marginTop": "8px"}),
        dcc.Dropdown(id="filter-source", multi=True, placeholder="Todas",
                     style={"fontSize": "0.78rem"}),
        html.Div(id="filter-info", style={"color": "#64748B", "fontSize": "0.72rem",
                                           "marginTop": "6px", "minHeight": "14px"}),
        html.Hr(style={"borderColor": "#334155", "margin": "10px 0"}),
    ], style={"padding": "0 1rem"}),

    # Género
    html.Div([
        html.Small("GÉNERO AUTORES", style={
            "color": "#94A3B8", "fontSize": "0.68rem", "fontWeight": "700",
            "letterSpacing": "0.08em", "display": "block", "marginBottom": "6px",
        }),
        dbc.Switch(id="gender-genderize", label="genderize.io API",
                   value=False, style={"color": "#CBD5E1", "fontSize": "0.78rem"}),
        dbc.Button("Analizar género", id="btn-gender", color="primary",
                   size="sm", className="mt-1 w-100"),
        html.Div(id="gender-status", style={"color": "#10B981", "fontSize": "0.72rem",
                                             "marginTop": "4px", "minHeight": "14px"}),
        html.Hr(style={"borderColor": "#334155", "margin": "10px 0"}),
    ], style={"padding": "0 1rem"}),

    # Descargar reporte
    html.Div([
        dbc.Button("📊 Descargar Excel", id="btn-download-report", color="warning",
                   size="sm", className="w-100", style={"marginBottom": "8px"}),
        dcc.Download(id="download-report"),
        html.Div(id="report-status", style={"color": "#94A3B8", "fontSize": "0.7rem",
                                             "textAlign": "center", "minHeight": "14px"}),
        html.Hr(style={"borderColor": "#334155", "margin": "8px 0"}),
    ], style={"padding": "0 1rem"}),

    # Navegación
    html.Div([
        html.Small("NAVEGACION", style={
            "color": "#94A3B8", "fontSize": "0.68rem", "fontWeight": "700",
            "letterSpacing": "0.08em", "display": "block", "marginBottom": "6px",
        }),
        *[html.A(label, href=f"#{anchor}", style={
            "display": "block", "color": "#CBD5E1", "textDecoration": "none",
            "fontSize": "0.78rem", "padding": "3px 0",
        }) for label, anchor in [
            ("Resumen", "resumen"), ("Produccion", "produccion"),
            ("Fuentes", "fuentes"), ("Autores", "autores"),
            ("Paises", "paises"), ("Documentos", "documentos"),
            ("Keywords", "keywords"), ("Synthesis", "synthesis"),
            ("Genero", "genero"), ("Redes", "redes"),
        ]],
    ], style={"padding": "0 1rem 1.5rem"}),

], style={
    "position": "fixed", "top": 0, "left": 0, "bottom": 0, "width": "230px",
    "background": "#1e293b", "overflowY": "auto", "zIndex": 1000,
})

# ── stores ────────────────────────────────────────────────────────────────────

STORES = html.Div([
    dcc.Store(id="data-version", data=0),
    dcc.Store(id="click-filters", data={"author": None, "institution": None, "year": None, "country": None}),
])

# ── estado vacío ──────────────────────────────────────────────────────────────

WELCOME = html.Div([
    html.Div([
        html.H2("Bienvenido a Scimap", style={"color": BLUE, "fontWeight": "700"}),
        html.P("Sube un archivo .bib / .txt de Scopus o WoS,  o busca directamente en OpenAlex.",
               style={"color": "#64748B", "fontSize": "1.05rem"}),
        html.Hr(),
        dbc.Row([
            dbc.Col([
                html.H5("Opción 1 — Archivo local", style={"color": BLUE}),
                html.P("Exporta tu búsqueda de Scopus o WoS en formato .bib o .txt y arrástralo al panel izquierdo."),
            ], width=6),
            dbc.Col([
                html.H5("Opción 2 — OpenAlex (sin archivo)", style={"color": GREEN}),
                html.P("Escribe el nombre de una institución y un tema en el panel izquierdo. Carga hasta 500 papers en segundos."),
            ], width=6),
        ]),
    ], style={"background": "white", "borderRadius": "12px", "padding": "2rem",
              "boxShadow": "0 1px 4px rgba(0,0,0,.07)", "marginTop": "2rem"}),
], id="welcome-panel")


# ── layout principal ──────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="Scimap",
    suppress_callback_exceptions=True,
)
server = app.server  # para gunicorn

app.layout = html.Div([
    SIDEBAR,
    STORES,
    html.Div([

        # Header
        html.Div([
            html.H1("Scimap", style={"fontSize": "1.7rem", "fontWeight": "700",
                                      "color": "white", "margin": 0}),
            html.P(id="header-subtitle",
                   children="Análisis bibliométrico inteligente",
                   style={"color": "rgba(255,255,255,.7)", "margin": "4px 0 0",
                          "fontSize": "0.9rem"}),
        ], style={"background": f"linear-gradient(135deg, #1e3a5f 0%, {BLUE} 100%)",
                  "padding": "1.5rem 2rem"}),

        html.Div([

            # Welcome o dashboard
            html.Div(id="dashboard-content"),

        ], style={"padding": "1.5rem 2rem"}),

        html.Footer(
            "Scimap · OpenAlex + Scopus/WoS",
            style={"textAlign": "center", "color": "#94A3B8",
                   "fontSize": "0.8rem", "padding": "1rem"},
        ),
    ], style={"marginLeft": "230px"}),
], style={"background": "#F1F5F9", "minHeight": "100vh"})


# ═════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ═════════════════════════════════════════════════════════════════════════════

# ── upload archivo ────────────────────────────────────────────────────────────

@callback(
    Output("upload-status", "children"),
    Output("data-version",  "data", allow_duplicate=True),
    Input("upload-data",    "contents"),
    State("upload-data",    "filename"),
    prevent_initial_call=True,
)
def handle_upload(contents, filename):
    global DF_FULL, DF_GENDER
    if not contents:
        return "", dash.no_update

    content_type, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    suffix  = Path(filename).suffix.lower()

    if suffix not in (".bib", ".txt", ".tsv", ".xlsx", ".xls"):
        return f"Formato no soportado: {suffix}", dash.no_update

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(decoded)
            tmp = f.name

        df = bp.load_data(Path(tmp))
        os.unlink(tmp)

        if df.empty:
            return "Archivo vacío o sin datos válidos.", dash.no_update

        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        DF_FULL   = df
        DF_GENDER = ge.gender_analysis_df(DF_FULL, use_genderize=False, use_web=False)

        return f"Cargado: {filename} ({len(df)} papers)", int(time.time())

    except Exception as e:
        return f"Error: {str(e)[:60]}", dash.no_update


# ── OpenAlex: buscar institución ──────────────────────────────────────────────

@callback(
    Output("oa-inst-results", "children"),
    Output("oa-inst-id",      "data"),
    Input("oa-institution",   "value"),
)
def search_institution(query):
    if not query or len(query) < 3:
        return "", None
    try:
        results = oa.search_institutions(query, n=4)
        if not results:
            return html.Small("Sin resultados", style={"color": RED}), None
        items = [
            html.Div(
                f"{r['name'][:30]} ({r['country']}) — {r['works_count']:,}",
                style={"color": "#CBD5E1", "fontSize": "0.7rem", "cursor": "pointer",
                       "padding": "3px 4px", "background": "#334155",
                       "borderRadius": "3px", "marginBottom": "2px"},
            )
            for r in results
        ]
        return html.Div(items), results[0]["id"]
    except Exception as e:
        return html.Small(f"Error: {e}", style={"color": RED}), None


# ── OpenAlex: buscar papers ───────────────────────────────────────────────────

@callback(
    Output("oa-status",    "children"),
    Output("data-version", "data", allow_duplicate=True),
    Input("btn-oa-search", "n_clicks"),
    State("oa-inst-id",    "data"),
    State("oa-keywords",   "value"),
    State("oa-years",      "value"),
    prevent_initial_call=True,
)
def run_oa_search(n_clicks, inst_id, keywords, years):
    global DF_FULL, DF_GENDER
    if not n_clicks:
        return "", dash.no_update
    if not inst_id and not keywords:
        return "Ingresa institución o tema.", dash.no_update

    y0, y1 = (years[0], years[1]) if years else (2022, 2025)
    concepts = [k.strip() for k in (keywords or "").split(",") if k.strip()]

    try:
        df = oa.fetch_works(
            institution_id=inst_id,
            keywords=keywords if not concepts else None,
            concept_names=concepts or None,
            year_from=y0, year_to=y1,
            max_results=500,
        )
        if df.empty:
            return "Sin resultados.", dash.no_update

        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        DF_FULL   = df
        DF_GENDER = ge.gender_analysis_df(DF_FULL, use_genderize=False, use_web=False)

        return f"OpenAlex: {len(df)} papers cargados", int(time.time())
    except Exception as e:
        return f"Error: {str(e)[:70]}", dash.no_update


# ── actualizar filtros cuando cambian los datos ────────────────────────────────

@callback(
    Output("filter-type",       "options"),
    Output("filter-source",     "options"),
    Output("filter-year",       "min"),
    Output("filter-year",       "max"),
    Output("filter-year",       "value"),
    Output("filter-year",       "marks"),
    Output("header-subtitle",   "children"),
    Input("data-version",       "data"),
)
def update_filters(version):
    if DF_FULL.empty:
        return [], [], 2018, 2026, [2018, 2026], {}, "Análisis bibliométrico inteligente"

    types   = sorted(DF_FULL["type"].dropna().unique())
    sources = sorted(DF_FULL["source"].dropna().unique())
    ymin    = int(DF_FULL["year"].min())
    ymax    = int(DF_FULL["year"].max())
    marks   = {y: {"label": str(y), "style": {"color": "#64748B", "fontSize": "0.7rem"}}
               for y in range(ymin, ymax + 1)}
    subtitle = f"{len(DF_FULL)} documentos · {', '.join(sources)} · {ymin}–{ymax}"

    return (
        [{"label": t.title(), "value": t} for t in types],
        [{"label": s, "value": s} for s in sources],
        ymin, ymax, [ymin, ymax], marks, subtitle,
    )


# ── dashboard content ─────────────────────────────────────────────────────────

@callback(
    Output("dashboard-content", "children"),
    Input("data-version",       "data"),
)
def render_dashboard(version):
    if DF_FULL.empty:
        return WELCOME

    nets_dir = Path(__file__).parent / "assets" / "networks"
    nets_dir.mkdir(parents=True, exist_ok=True)

    # Generar redes
    import visualizer as viz
    G_coauth = an.coauthorship_network(DF_FULL)
    G_kw     = an.keyword_cooccurrence_network(DF_FULL, min_freq=2)
    viz.network_to_pyvis_html(G_coauth, "Co-autoria",    nets_dir / "coauthorship.html")
    viz.network_to_pyvis_html(G_kw,     "Co-ocurrencia", nets_dir / "keywords.html")

    return html.Div([

        # KPIs
        html.Div(id="resumen"),
        dbc.Row([
            dbc.Col(stat_card("stat-docs",    "Documentos",    BLUE),   width=3),
            dbc.Col(stat_card("stat-authors", "Autores",       GREEN),  width=3),
            dbc.Col(stat_card("stat-cites",   "Citas totales", AMBER),  width=3),
            dbc.Col(stat_card("stat-hindex",  "H-index",       RED),    width=3),
        ], className="g-3 mb-2"),
        dbc.Row([
            dbc.Col(stat_card("stat-sources", "Journals",      PURPLE), width=3),
            dbc.Col(stat_card("stat-collab",  "Colab. index",  PINK),   width=3),
            dbc.Col(stat_card("stat-avgcit",  "Citas prom.",   BLUE),   width=3),
            dbc.Col(stat_card("stat-years",   "Periodo",       GRAY),   width=3),
        ], className="g-3 mb-3"),

        # Produccion
        section_header("PRODUCCION"),
        html.Div(id="produccion"),
        dbc.Row([
            dbc.Col(card([html.H6("Produccion por ano"),  dcc.Graph(id="chart-year")]),      width=8),
            dbc.Col(card([html.H6("Tipos de documento"),  dcc.Graph(id="chart-types")]),     width=4),
        ], className="g-3"),
        dbc.Row([
            dbc.Col(card([html.H6("Ciclo de vida"),       dcc.Graph(id="chart-lifecycle")]), width=6),
            dbc.Col(card([html.H6("Citas promedio/ano"),  dcc.Graph(id="chart-acpy")]),      width=6),
        ], className="g-3"),

        # Fuentes
        section_header("FUENTES"),
        html.Div(id="fuentes"),
        dbc.Row([
            dbc.Col(card([html.H6("Top journals"),    dcc.Graph(id="chart-sources")]),   width=6),
            dbc.Col(card([html.H6("Ley de Bradford"), dcc.Graph(id="chart-bradford")]),  width=6),
        ], className="g-3"),

        # Autores
        section_header("AUTORES"),
        html.Div(id="autores"),
        dbc.Row([
            dbc.Col(card([html.H6("Autores mas productivos"), dcc.Graph(id="chart-authors")]), width=6),
            dbc.Col(card([html.H6("Ley de Lotka"),            dcc.Graph(id="chart-lotka")]),   width=6),
        ], className="g-3"),
        card([html.H6("Afiliaciones frecuentes"), dcc.Graph(id="chart-affiliations")]),

        # Paises
        section_header("PAISES"),
        html.Div(id="paises"),
        card([html.H6("Mapa de produccion"),        dcc.Graph(id="chart-map")]),
        card([html.H6("Paises en el tiempo"),       dcc.Graph(id="chart-countries-time")]),

        # Documentos
        section_header("DOCUMENTOS"),
        html.Div(id="documentos"),
        dbc.Row([
            dbc.Col(card([html.H6("Mas citados"),   dcc.Graph(id="chart-citations")]), width=7),
            dbc.Col(card([html.H6("Open Access"),   dcc.Graph(id="chart-oa")]),        width=5),
        ], className="g-3"),
        card([html.H6("Tabla: articulos mas citados"), html.Div(id="table-citations")]),

        # Keywords
        section_header("KEYWORDS"),
        html.Div(id="keywords"),
        dbc.Row([
            dbc.Col(card([html.H6("TreeMap"),    dcc.Graph(id="chart-treemap")]),   width=7),
            dbc.Col(card([html.H6("Word Cloud"), dcc.Graph(id="chart-wordcloud")]), width=5),
        ], className="g-3"),
        dbc.Row([
            dbc.Col(card([html.H6("Trend Topics"),       dcc.Graph(id="chart-trend")]),     width=6),
            dbc.Col(card([html.H6("Crecimiento CAGR"),   dcc.Graph(id="chart-kw-growth")]), width=6),
        ], className="g-3"),
        card([html.H6("Keywords en el tiempo"), dcc.Graph(id="chart-kw-time")]),

        # Synthesis
        section_header("SYNTHESIS"),
        html.Div(id="synthesis"),
        dbc.Row([
            dbc.Col(card([html.H6("Three-Field Plot"),  dcc.Graph(id="chart-sankey")]),   width=6),
            dbc.Col(card([html.H6("Mapa Tematico"),     dcc.Graph(id="chart-thematic")]), width=6),
        ], className="g-3"),
        card([html.H6("TF-IDF Abstracts"), dcc.Graph(id="chart-tfidf")]),

        # Genero
        section_header("GENERO DE PRIMER AUTOR"),
        html.Div(id="genero"),
        dbc.Row([
            dbc.Col(card([html.H6("Distribucion"),  dcc.Graph(id="chart-gender-pie")]),   width=5),
            dbc.Col(card([html.H6("Ratio M/F"),     dcc.Graph(id="chart-gender-ratio")]), width=7),
        ], className="g-3"),
        card([html.H6("Por ano"), dcc.Graph(id="chart-gender-year")]),
        card([html.H6("Detalle"), html.Div(id="table-gender"),
              html.Div(id="gender-coverage", style={"fontSize": "0.8rem", "color": "#64748B"})]),

        # Redes
        section_header("REDES"),
        html.Div(id="redes"),
        dbc.Row([
            dbc.Col(card([
                html.H6("Red de co-autoria"),
                html.Iframe(src="/assets/networks/coauthorship.html",
                            style={"width": "100%", "height": "480px", "border": "none"}),
            ]), width=6),
            dbc.Col(card([
                html.H6("Red de co-ocurrencia keywords"),
                html.Iframe(src="/assets/networks/keywords.html",
                            style={"width": "100%", "height": "480px", "border": "none"}),
            ]), width=6),
        ], className="g-3"),
    ])


# ═════════════════════════════════════════════════════════════════════════════
# CALLBACKS DE GRÁFICOS
# ═════════════════════════════════════════════════════════════════════════════

@callback(
    Output("filter-info",  "children"),
    Output("stat-docs",    "children"),
    Output("stat-authors", "children"),
    Output("stat-cites",   "children"),
    Output("stat-hindex",  "children"),
    Output("stat-sources", "children"),
    Output("stat-collab",  "children"),
    Output("stat-avgcit",  "children"),
    Output("stat-years",   "children"),
    Input("filter-year",   "value"),
    Input("filter-type",   "value"),
    Input("filter-source", "value"),
    Input("data-version",  "data"),
)
def update_stats(years, types, sources, _):
    df = filter_df(years, types or [], sources or [])
    if df.empty:
        return ("Sin datos",) + ("—",) * 8
    s = an.summary_stats(df)
    return (
        f"{len(df)} de {len(DF_FULL)} docs",
        s["total_documents"], s["total_authors"],
        f"{s['total_citations']:,}", s["h_index"],
        s["total_sources"], s["collaboration_index"],
        s["avg_citations"], s["years_range"],
    )


@callback(
    Output("chart-year",      "figure"),
    Output("chart-types",     "figure"),
    Output("chart-lifecycle", "figure"),
    Output("chart-acpy",      "figure"),
    Input("filter-year",      "value"),
    Input("filter-type",      "value"),
    Input("filter-source",    "value"),
    Input("data-version",     "data"),
    Input("click-filters",    "data"),
    prevent_initial_call=False,
)
def update_production(years, types, sources, _, click_filters):
    df = filter_df(years, types or [], sources or [], click_filters)
    if df.empty:
        return _empty_fig(), _empty_fig(), _empty_fig(), _empty_fig()

    dy  = an.production_by_year(df)
    dlc = an.life_cycle(df)
    da  = an.avg_citations_per_year(df)
    dt  = an.document_types(df)

    f1 = go.Figure(go.Bar(x=dy["year"], y=dy["count"], marker_color=BLUE,
                           text=dy["count"], textposition="outside"))
    _fig_layout(f1)

    f2 = go.Figure(go.Pie(labels=dt["type"], values=dt["count"], hole=0.4,
                           marker_colors=PALETTE))
    f2.update_layout(paper_bgcolor=BG, margin=dict(t=10, b=10), height=360)

    f3 = go.Figure()
    f3.add_trace(go.Bar(x=dlc["year"], y=dlc["count"], name="Anual",
                         marker_color="#93C5FD", opacity=0.7))
    f3.add_trace(go.Scatter(x=dlc["year"], y=dlc["cumulative"], name="Acumulado",
                             line=dict(color=BLUE, width=3), yaxis="y2"))
    f3.update_layout(yaxis2=dict(overlaying="y", side="right"),
                      legend=dict(orientation="h", y=-0.2),
                      plot_bgcolor=BG, paper_bgcolor=BG, height=360,
                      margin=dict(t=10, b=30))

    f4 = go.Figure(go.Scatter(x=da["year"], y=da["acpy"], mode="lines+markers",
                               line=dict(color=GREEN, width=3),
                               fill="tozeroy", fillcolor="rgba(16,185,129,0.1)"))
    _fig_layout(f4)

    return f1, f2, f3, f4


@callback(
    Output("chart-sources",  "figure"),
    Output("chart-bradford", "figure"),
    Input("filter-year",     "value"),
    Input("filter-type",     "value"),
    Input("filter-source",   "value"),
    Input("data-version",    "data"),
    Input("click-filters",   "data"),
    prevent_initial_call=False,
)
def update_sources(years, types, sources, _, click_filters):
    df = filter_df(years, types or [], sources or [], click_filters)
    if df.empty:
        return _empty_fig(), _empty_fig()

    ds   = an.top_sources(df).sort_values("count")
    ds["j"] = ds["journal"].apply(lambda x: x[:40] + "..." if len(x) > 40 else x)
    f1 = go.Figure(go.Bar(x=ds["count"], y=ds["j"], orientation="h",
                           marker_color=BLUE, text=ds["count"], textposition="outside"))
    _fig_layout(f1, max(320, len(ds) * 28))

    brad = an.bradford_law(df)
    det  = brad["detail"]
    zc   = {1: BLUE, 2: GREEN, 3: AMBER}
    f2 = go.Figure(go.Bar(x=det["rank"], y=det["count"],
                           marker_color=[zc.get(z, GRAY) for z in det["zone"]],
                           hovertext=det["journal"], hoverinfo="text+y"))
    _fig_layout(f2)
    return f1, f2


@callback(
    Output("chart-authors",      "figure"),
    Output("chart-lotka",        "figure"),
    Output("chart-affiliations", "figure"),
    Input("filter-year",         "value"),
    Input("filter-type",         "value"),
    Input("filter-source",       "value"),
    Input("data-version",        "data"),
    Input("click-filters",       "data"),
    prevent_initial_call=False,
)
def update_authors(years, types, sources, _, click_filters):
    df = filter_df(years, types or [], sources or [], click_filters)
    if df.empty:
        return _empty_fig(), _empty_fig(), _empty_fig()

    da   = an.top_authors(df).sort_values("count")
    f1 = go.Figure(go.Bar(x=da["count"], y=da["author"], orientation="h",
                           marker_color=GREEN, text=da["count"], textposition="outside"))
    _fig_layout(f1, max(320, len(da) * 26))

    dl = an.lotka_law(df)
    f2 = go.Figure()
    f2.add_trace(go.Bar(x=dl["papers"], y=dl["authors"], name="Observado",
                         marker_color=BLUE, opacity=0.8))
    f2.add_trace(go.Scatter(x=dl["papers"], y=dl["expected"], name="Esperado",
                             mode="lines+markers", line=dict(color=RED, dash="dash")))
    f2.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=360,
                      legend=dict(orientation="h", y=-0.2), margin=dict(t=10))

    daff = an.top_affiliations(df).sort_values("count")
    daff["a"] = daff["affiliation"].apply(lambda x: x[:50] + "..." if len(x) > 50 else x)
    f3 = go.Figure(go.Bar(x=daff["count"], y=daff["a"], orientation="h",
                           marker_color=PURPLE, text=daff["count"], textposition="outside"))
    _fig_layout(f3, max(320, len(daff) * 26))

    return f1, f2, f3


@callback(
    Output("chart-map",            "figure"),
    Output("chart-countries-time", "figure"),
    Input("filter-year",           "value"),
    Input("filter-type",           "value"),
    Input("filter-source",         "value"),
    Input("data-version",          "data"),
    Input("click-filters",         "data"),
    prevent_initial_call=False,
)
def update_countries(years, types, sources, _, click_filters):
    df = filter_df(years, types or [], sources or [], click_filters)
    if df.empty:
        return _empty_fig(), _empty_fig()

    dc = an.top_countries(df)
    f1 = go.Figure(go.Choropleth(
        locations=dc["country"], locationmode="country names", z=dc["count"],
        colorscale="Blues", colorbar_title="Publicaciones",
    ))
    f1.update_layout(geo=dict(showframe=False), margin=dict(l=0, r=0, t=10, b=0),
                      paper_bgcolor=BG, height=400)

    dct = an.countries_production_over_time(df)
    f2 = px.line(dct, x="year", y="count", color="country", markers=True)
    f2.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=360,
                      legend=dict(orientation="h", y=-0.3), margin=dict(t=10))
    return f1, f2


@callback(
    Output("chart-citations", "figure"),
    Output("chart-oa",        "figure"),
    Output("table-citations", "children"),
    Input("filter-year",      "value"),
    Input("filter-type",      "value"),
    Input("filter-source",    "value"),
    Input("data-version",     "data"),
    Input("click-filters",    "data"),
    prevent_initial_call=False,
)
def update_documents(years, types, sources, _, click_filters):
    df = filter_df(years, types or [], sources or [], click_filters)
    if df.empty:
        return _empty_fig(), _empty_fig(), ""

    dc = an.citation_summary(df).head(15).copy()
    dc["title_s"] = dc["title"].apply(lambda x: x[:55] + "..." if len(x) > 55 else x)
    dcs = dc.sort_values("cited_by")
    f1 = go.Figure(go.Bar(x=dcs["cited_by"], y=dcs["title_s"], orientation="h",
                           marker_color=AMBER, text=dcs["cited_by"], textposition="outside"))
    _fig_layout(f1, max(360, len(dcs) * 32))

    doa = an.open_access_breakdown(df)
    f2 = go.Figure(go.Pie(labels=doa["type"], values=doa["count"], hole=0.4,
                           marker_colors=[GREEN, BLUE, PURPLE, GRAY]))
    f2.update_layout(paper_bgcolor=BG, margin=dict(t=10, b=10), height=360)

    dc["authors_s"] = dc["authors"].apply(
        lambda x: ", ".join(x[:2]) + (" et al." if len(x) > 2 else "") if isinstance(x, list) else x
    )
    tbl = dash_table.DataTable(
        data=dc[["title_s", "authors_s", "year", "journal", "cited_by"]].rename(
            columns={"title_s": "Titulo", "authors_s": "Autores",
                     "year": "Ano", "journal": "Journal", "cited_by": "Citas"}
        ).to_dict("records"),
        columns=[{"name": c, "id": c} for c in ["Titulo", "Autores", "Ano", "Journal", "Citas"]],
        style_table={"overflowX": "auto"},
        style_cell={"fontSize": "0.83rem", "padding": "6px 10px"},
        style_header={"fontWeight": "700", "background": "#F8FAFC"},
        style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#F8FAFC"}],
        page_size=10, sort_action="native",
    )
    return f1, f2, tbl


@callback(
    Output("chart-treemap",   "figure"),
    Output("chart-wordcloud", "figure"),
    Output("chart-trend",     "figure"),
    Output("chart-kw-growth", "figure"),
    Output("chart-kw-time",   "figure"),
    Input("filter-year",      "value"),
    Input("filter-type",      "value"),
    Input("filter-source",    "value"),
    Input("data-version",     "data"),
    Input("click-filters",    "data"),
    prevent_initial_call=False,
)
def update_keywords(years, types, sources, _, click_filters):
    df = filter_df(years, types or [], sources or [], click_filters)
    if df.empty:
        return [_empty_fig()] * 5

    dkw = an.top_keywords(df)

    f1 = px.treemap(dkw, path=["keyword"], values="count",
                     color="count", color_continuous_scale="Blues")
    f1.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=400)

    max_c = dkw["count"].max() if not dkw.empty else 1
    np.random.seed(42)
    x = np.random.uniform(0, 10, len(dkw))
    y = np.random.uniform(0, 10, len(dkw))
    sizes = (10 + 40 * (dkw["count"] / max_c)).tolist()
    f2 = go.Figure(go.Scatter(
        x=x, y=y, mode="text", text=dkw["keyword"],
        textfont=dict(size=sizes, color=[
            f"rgb({int(30+200*(1-c/max_c))},{int(80+100*(c/max_c))},{int(220*(c/max_c))})"
            for c in dkw["count"]
        ]),
        hovertext=[f"{k}: {c}" for k, c in zip(dkw["keyword"], dkw["count"])],
        hoverinfo="text",
    ))
    f2.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="#F8FAFC", paper_bgcolor=BG, height=400, margin=dict(t=10),
    )

    dtr = an.trend_topics(df)
    if not dtr.empty:
        period_cols = [c for c in dtr.columns if c.startswith("P")]
        f3 = go.Figure()
        for _, row in dtr.iterrows():
            vals  = [row[c] for c in period_cols]
            color = GREEN if row.get("growth", 0) > 0 else RED
            f3.add_trace(go.Scatter(
                x=period_cols, y=vals, name=row["keyword"],
                mode="lines+markers+text",
                text=[None] * (len(period_cols) - 1) + [row["keyword"]],
                textposition="middle right",
                line=dict(color=color, width=2),
            ))
        f3.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=400,
                          showlegend=False, margin=dict(t=10, r=80))
    else:
        f3 = _empty_fig("Se necesitan al menos 2 anos de datos")

    dgr = an.keyword_growth_rate(df).head(20)
    if not dgr.empty:
        dgr = dgr.sort_values("cagr")
        f4 = go.Figure(go.Bar(
            x=dgr["cagr"], y=dgr["keyword"], orientation="h",
            marker_color=[GREEN if g > 0 else RED for g in dgr["cagr"]],
            text=[f"{g:+.1f}%" for g in dgr["cagr"]], textposition="outside",
        ))
        _fig_layout(f4, max(360, len(dgr) * 28))
    else:
        f4 = _empty_fig()

    dwt = an.words_frequency_over_time(df)
    if not dwt.empty:
        f5 = px.line(dwt, x="year", y="count", color="keyword", markers=True)
        f5.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=400,
                          legend=dict(orientation="h", y=-0.3), margin=dict(t=10))
    else:
        f5 = _empty_fig()

    return f1, f2, f3, f4, f5


@callback(
    Output("chart-sankey",   "figure"),
    Output("chart-thematic", "figure"),
    Output("chart-tfidf",    "figure"),
    Input("filter-year",     "value"),
    Input("filter-type",     "value"),
    Input("filter-source",   "value"),
    Input("data-version",    "data"),
    Input("click-filters",   "data"),
    prevent_initial_call=False,
)
def update_synthesis(years, types, sources, _, click_filters):
    df = filter_df(years, types or [], sources or [], click_filters)
    if df.empty:
        return _empty_fig(), _empty_fig(), _empty_fig()

    sd = an.three_field_data(df)
    if sd["sources"]:
        f1 = go.Figure(go.Sankey(
            node=dict(label=sd["labels"], pad=12, thickness=18,
                      color=[PALETTE[i % len(PALETTE)] for i in range(len(sd["labels"]))]),
            link=dict(source=sd["sources"], target=sd["targets"], value=sd["values"],
                      color="rgba(37,99,235,0.2)"),
        ))
        f1.update_layout(paper_bgcolor=BG, height=480, margin=dict(t=10), font_size=11)
    else:
        f1 = _empty_fig("Sin datos suficientes para Sankey")

    dtm = an.thematic_map(df)
    qc  = {"Motor themes": BLUE, "Niche themes": GREEN,
           "Basic themes": AMBER, "Emerging themes": RED}
    if not dtm.empty:
        f2 = go.Figure()
        for q, color in qc.items():
            sub = dtm[dtm["quadrant"] == q]
            if sub.empty:
                continue
            f2.add_trace(go.Scatter(
                x=sub["centrality"], y=sub["density"],
                mode="markers+text", name=q, text=sub["label"],
                textposition="top center",
                marker=dict(size=sub["size"] * 6 + 10, color=color, opacity=0.75),
                hovertext=sub["keywords"],
            ))
        f2.add_hline(y=dtm["density"].median(), line_dash="dot", line_color=GRAY)
        f2.add_vline(x=dtm["centrality"].median(), line_dash="dot", line_color=GRAY)
        f2.update_layout(plot_bgcolor="#F8FAFC", paper_bgcolor=BG, height=480,
                          legend=dict(orientation="h", y=-0.15), margin=dict(t=10))
    else:
        f2 = _empty_fig("Sin datos suficientes para mapa tematico")

    dti = an.abstract_tfidf(df)
    if not dti.empty:
        dti = dti.sort_values("tfidf")
        f3 = go.Figure(go.Bar(x=dti["tfidf"], y=dti["term"], orientation="h",
                               marker_color="#0EA5E9",
                               text=dti["tfidf"].round(3), textposition="outside"))
        _fig_layout(f3, max(360, len(dti) * 26))
    else:
        f3 = _empty_fig("Sin abstracts disponibles")

    return f1, f2, f3


# ── género ────────────────────────────────────────────────────────────────────

GENDER_COLORS = {
    "Masculino": "#2563EB", "Femenino": "#EC4899",
    "Ambiguo":   "#F59E0B", "Desconocido": "#94A3B8",
}


@callback(
    Output("chart-gender-pie",   "figure"),
    Output("chart-gender-ratio", "figure"),
    Output("chart-gender-year",  "figure"),
    Output("table-gender",       "children"),
    Output("gender-coverage",    "children"),
    Output("gender-status",      "children"),
    Input("btn-gender",          "n_clicks"),
    Input("gender-genderize",    "value"),
    Input("filter-year",         "value"),
    Input("filter-type",         "value"),
    Input("filter-source",       "value"),
    Input("data-version",        "data"),
    Input("click-filters",       "data"),
    prevent_initial_call=False,
)
def update_gender(n_clicks, use_genderize, years, types, sources, _, click_filters):
    global DF_GENDER
    df_base = filter_df(years, types or [], sources or [], click_filters)
    if df_base.empty:
        return [_empty_fig()] * 3 + ["", "", "Sin datos"]

    if ctx.triggered_id == "btn-gender" and n_clicks:
        DF_GENDER = ge.gender_analysis_df(df_base, use_genderize=use_genderize, use_web=False)
    elif DF_GENDER.empty or len(DF_GENDER) != len(df_base):
        DF_GENDER = ge.gender_analysis_df(df_base, use_genderize=False, use_web=False)

    summary  = ge.gender_summary(DF_GENDER)
    vc       = summary["overall"]
    by_year  = summary["by_year"]
    coverage = summary["coverage"]
    detail   = summary["author_detail"]

    vc_cols = list(vc.columns)
    g_col, c_col = vc_cols[0], vc_cols[1]
    colors = [GENDER_COLORS.get(g, GRAY) for g in vc[g_col]]

    f1 = go.Figure(go.Pie(labels=vc[g_col], values=vc[c_col], hole=0.45,
                           marker_colors=colors, textinfo="label+percent"))
    f1.update_layout(paper_bgcolor=BG, margin=dict(t=10, b=10), height=360, showlegend=False)

    f2 = go.Figure()
    if not by_year.empty:
        ratio_rows = []
        for yr, grp in by_year.groupby("year"):
            m = grp.loc[grp["genero"] == "Masculino",  "count"].sum()
            f = grp.loc[grp["genero"] == "Femenino",   "count"].sum()
            if f > 0:
                ratio_rows.append({"year": yr, "ratio": round(m / f, 2)})
        if ratio_rows:
            dr = pd.DataFrame(ratio_rows)
            f2.add_trace(go.Scatter(
                x=dr["year"], y=dr["ratio"], mode="lines+markers+text",
                text=dr["ratio"], textposition="top center",
                line=dict(color=BLUE, width=3),
                fill="tozeroy", fillcolor="rgba(37,99,235,0.1)",
            ))
            f2.add_hline(y=1, line_dash="dot", line_color=GREEN,
                          annotation_text="Paridad", annotation_position="right")
    f2.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=360,
                      xaxis_title="Ano", yaxis_title="Ratio M/F", margin=dict(t=10))

    f3 = go.Figure()
    if not by_year.empty:
        for gender, color in GENDER_COLORS.items():
            sub = by_year[by_year["genero"] == gender]
            if not sub.empty:
                f3.add_trace(go.Bar(x=sub["year"], y=sub["count"],
                                     name=gender, marker_color=color))
        f3.update_layout(barmode="stack", plot_bgcolor=BG, paper_bgcolor=BG, height=360,
                          legend=dict(orientation="h", y=-0.2), margin=dict(t=10))

    det = detail[["primer_autor", "primer_nombre", "genero", "metodo_inferencia", "confianza"]].head(50)
    det.columns = ["Autor", "Primer nombre", "Genero", "Metodo", "Confianza"]
    tbl = dash_table.DataTable(
        data=det.to_dict("records"),
        columns=[{"name": c, "id": c} for c in det.columns],
        style_table={"overflowX": "auto"},
        style_cell={"fontSize": "0.82rem", "padding": "5px 8px"},
        style_header={"fontWeight": "700", "background": "#F8FAFC"},
        style_data_conditional=[
            {"if": {"filter_query": '{Genero} = "Masculino"'}, "backgroundColor": "#EFF6FF"},
            {"if": {"filter_query": '{Genero} = "Femenino"'},  "backgroundColor": "#FDF2F8"},
        ],
        page_size=15, sort_action="native",
    )

    methods_str = " | ".join(f"{m}: {n}" for m, n in summary["methods"].items())
    return (
        f1, f2, f3, tbl,
        f"Cobertura: {coverage}% — {methods_str}",
        f"Listo — {coverage}% cobertura",
    )


# ── descargar reporte Excel ───────────────────────────────────────────────────

@callback(
    Output("download-report", "data"),
    Output("report-status", "children"),
    Input("btn-download-report", "n_clicks"),
    prevent_initial_call=True,
)
def download_excel_report(n_clicks):
    """Genera y descarga reporte Excel profesional."""
    try:
        import excel_report as er

        if DF_FULL.empty:
            return dash.no_update, "Sin datos para exportar"

        # Generar reporte
        output_path = Path(tempfile.gettempdir()) / f"scimap_{int(time.time())}.xlsx"
        er.generate_report(DF_FULL, str(output_path))

        # Enviar para descargar
        return dcc.send_file(str(output_path)), "Listo"

    except Exception as e:
        return dash.no_update, f"Error: {str(e)[:30]}"


# ── callbacks interactivos: click-to-filter ───────────────────────────────────

@callback(
    Output("click-filters", "data"),
    Input("chart-authors",      "clickData"),
    Input("chart-affiliations", "clickData"),
    Input("chart-year",         "clickData"),
    Input("chart-map",          "clickData"),
    State("click-filters",      "data"),
    prevent_initial_call=True,
)
def update_click_filters(author_click, affil_click, year_click, map_click, current_filters):
    """Detecta clicks en gráficos y actualiza filtros interactivos."""
    if not current_filters:
        current_filters = {"author": None, "institution": None, "year": None, "country": None}

    # Detectar cuál gráfico fue clickeado
    triggered = [t["prop_id"] for t in ctx.triggered if t["value"]]
    if not triggered:
        return current_filters

    triggered_id = triggered[0].split(".")[0]

    # Click en autores
    if triggered_id == "chart-authors" and author_click:
        try:
            label = author_click["points"][0].get("customdata") or author_click["points"][0].get("label")
            current_filters["author"] = label if label != current_filters.get("author") else None
        except:
            pass

    # Click en afiliaciones
    elif triggered_id == "chart-affiliations" and affil_click:
        try:
            label = affil_click["points"][0].get("customdata") or affil_click["points"][0].get("label")
            current_filters["institution"] = label if label != current_filters.get("institution") else None
        except:
            pass

    # Click en año
    elif triggered_id == "chart-year" and year_click:
        try:
            year = int(year_click["points"][0].get("x"))
            current_filters["year"] = year if year != current_filters.get("year") else None
        except:
            pass

    # Click en mapa
    elif triggered_id == "chart-map" and map_click:
        try:
            country = map_click["points"][0].get("customdata") or map_click["points"][0].get("label")
            current_filters["country"] = country if country != current_filters.get("country") else None
        except:
            pass

    return current_filters


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, port=8050)
