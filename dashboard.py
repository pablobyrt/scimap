"""
Genera el dashboard HTML completo.
"""
from pathlib import Path
import pandas as pd
import analysis as an
import visualizer as viz

_CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #F1F5F9; color: #1e293b; }

/* Header */
header { background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
         color: white; padding: 2rem 2.5rem; }
header h1 { font-size: 1.9rem; font-weight: 700; letter-spacing: -.5px; }
header p  { opacity: .75; margin-top: .3rem; font-size: .95rem; }

/* Nav lateral */
nav { position: fixed; top: 0; left: 0; width: 220px; height: 100vh;
      background: #1e293b; overflow-y: auto; z-index: 100; padding-top: 1rem;
      display: flex; flex-direction: column; }
nav .logo { color: white; font-weight: 700; font-size: 1rem; padding: .8rem 1.2rem;
            border-bottom: 1px solid #334155; margin-bottom: .5rem; }
nav .nav-section { color: #94A3B8; font-size: .68rem; font-weight: 700; letter-spacing: .08em;
                   text-transform: uppercase; padding: .8rem 1.2rem .3rem; }
nav a { display: block; color: #CBD5E1; text-decoration: none; padding: .45rem 1.2rem;
        font-size: .82rem; border-left: 3px solid transparent; transition: all .15s; }
nav a:hover { color: white; background: #334155; border-left-color: #2563eb; }

/* Layout */
.main { margin-left: 220px; }
.hero { background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
        color: white; padding: 2rem 2.5rem; }
.hero h1 { font-size: 1.7rem; font-weight: 700; }
.hero p  { opacity: .75; margin-top: .3rem; }

/* Stats */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
              gap: 1rem; padding: 1.5rem 2rem; }
.stat-card { background: white; border-radius: 10px; padding: 1.2rem 1.4rem;
             box-shadow: 0 1px 4px rgba(0,0,0,.08); border-top: 3px solid #2563eb; }
.stat-card .value { font-size: 2rem; font-weight: 700; color: #2563eb; }
.stat-card .label { font-size: .75rem; color: #64748b; margin-top: .2rem;
                    text-transform: uppercase; letter-spacing: .05em; }

/* Sections */
.section { background: white; margin: 0 2rem 1.5rem; border-radius: 12px;
           padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,.07); }
.section h2 { font-size: 1.05rem; font-weight: 600; margin-bottom: 1rem; color: #1e293b;
              border-bottom: 2px solid #e2e8f0; padding-bottom: .5rem; display: flex;
              align-items: center; gap: .4rem; }
.section-label { font-size: .7rem; background: #EFF6FF; color: #2563EB; border-radius: 99px;
                 padding: .15rem .5rem; font-weight: 600; letter-spacing: .04em; }

/* Two column */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;
           margin: 0 2rem 1.5rem; }
.two-col .section { margin: 0; }

/* Three column */
.three-col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1.5rem;
             margin: 0 2rem 1.5rem; }
.three-col .section { margin: 0; }

/* Section title divider */
.divider { padding: .5rem 2rem .2rem; }
.divider h3 { font-size: .75rem; font-weight: 700; color: #64748b; letter-spacing: .1em;
              text-transform: uppercase; display: flex; align-items: center; gap: .5rem; }
.divider h3::after { content: ''; flex: 1; height: 1px; background: #E2E8F0; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: .86rem; }
th { background: #f8fafc; padding: .55rem .8rem; text-align: left; font-weight: 600;
     border-bottom: 2px solid #e2e8f0; white-space: nowrap; }
td { padding: .45rem .8rem; border-bottom: 1px solid #f1f5f9; }
tr:hover td { background: #f8fafc; }

/* Network iframes */
iframe.net-frame { width: 100%; height: 540px; border: none; border-radius: 8px; }

/* Badges */
.badge { display: inline-block; background: #EFF6FF; color: #2563EB; border-radius: 99px;
         padding: .15rem .6rem; font-size: .75rem; font-weight: 600; margin: .1rem; }
.badge.green { background: #F0FDF4; color: #15803D; }
.badge.amber { background: #FFFBEB; color: #B45309; }

/* New tag */
.new-tag { background: #10B981; color: white; border-radius: 4px; padding: .1rem .35rem;
           font-size: .65rem; font-weight: 700; vertical-align: middle; margin-left: .3rem; }

/* Footer */
footer { text-align: center; padding: 2rem; color: #94a3b8; font-size: .8rem; margin-left: 220px; }

@media(max-width: 900px) {
  nav { display: none; }
  .main, footer { margin-left: 0; }
  .two-col, .three-col { grid-template-columns: 1fr; }
}
</style>
"""

_NAV = """
<nav>
  <div class="logo">Bibliometrix</div>
  <div class="nav-section">Descripcion</div>
  <a href="#overview">Resumen general</a>
  <div class="nav-section">Produccion</div>
  <a href="#produccion-anual">Produccion por ano</a>
  <a href="#ciclo-vida">Ciclo de vida</a>
  <a href="#citas-por-ano">Citas por ano</a>
  <div class="nav-section">Fuentes</div>
  <a href="#top-journals">Top journals</a>
  <a href="#bradford">Ley de Bradford</a>
  <a href="#journals-tiempo">Journals en el tiempo</a>
  <div class="nav-section">Autores</div>
  <a href="#top-autores">Autores productivos</a>
  <a href="#lotka">Ley de Lotka</a>
  <a href="#autores-tiempo">Autores en el tiempo</a>
  <a href="#afiliaciones">Afiliaciones</a>
  <div class="nav-section">Paises</div>
  <a href="#mapa">Mapa mundial</a>
  <a href="#paises-tiempo">Paises en el tiempo</a>
  <div class="nav-section">Documentos</div>
  <a href="#mas-citados">Mas citados</a>
  <a href="#tipos-doc">Tipos</a>
  <a href="#open-access">Open Access</a>
  <a href="#publishers">Publishers</a>
  <div class="nav-section">Keywords</div>
  <a href="#treemap">TreeMap</a>
  <a href="#wordcloud">WordCloud</a>
  <a href="#keywords-tiempo">Keywords en el tiempo</a>
  <a href="#trend-topics">Trend Topics</a>
  <a href="#keyword-growth">Crecimiento</a>
  <div class="nav-section">Synthesis</div>
  <a href="#sankey">Three-Field Plot</a>
  <a href="#mapa-tematico">Mapa Tematico</a>
  <a href="#abstracts">TF-IDF Abstracts</a>
  <a href="#edad-citas">Edad publicaciones</a>
  <div class="nav-section">Redes</div>
  <a href="#red-coautoria">Co-autoria</a>
  <a href="#red-coocurrencia">Co-ocurrencia</a>
  <a href="#red-cocitacion">Co-citacion</a>
  <a href="#red-paises">Colaboracion paises</a>
</nav>
"""


def _stat(value, label, color="#2563eb") -> str:
    return f'<div class="stat-card"><div class="value" style="color:{color}">{value}</div><div class="label">{label}</div></div>'


def _section(anchor: str, title: str, content: str, badge: str = "", new: bool = False) -> str:
    badge_html = f'<span class="section-label">{badge}</span>' if badge else ""
    new_html = '<span class="new-tag">NUEVO</span>' if new else ""
    return f'<div class="section" id="{anchor}"><h2>{title} {badge_html}{new_html}</h2>{content}</div>'


def _table(df: pd.DataFrame, max_rows: int = 20) -> str:
    rows = ""
    for _, row in df.head(max_rows).iterrows():
        cells = "".join(f"<td>{_format_cell(v)}</td>" for v in row)
        rows += f"<tr>{cells}</tr>"
    headers = "".join(f"<th>{c}</th>" for c in df.columns)
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>"


def _format_cell(v):
    if isinstance(v, list):
        return ", ".join(str(i) for i in v[:3]) + (" ..." if len(v) > 3 else "")
    return v


def _divider(title: str) -> str:
    return f'<div class="divider"><h3>{title}</h3></div>'


def _iframe(path: Path, exists: bool) -> str:
    if exists:
        return f'<iframe class="net-frame" src="networks/{path.name}"></iframe>'
    return "<p style='color:#94a3b8;'>Sin datos suficientes para la red.</p>"


def build_dashboard(df: pd.DataFrame, output_path: str | Path = "dashboard.html"):
    output_path = Path(output_path)
    nets_dir = output_path.parent / "networks"
    nets_dir.mkdir(exist_ok=True)

    stats = an.summary_stats(df)

    # ── calcular todo ──────────────────────────────────────────────────────
    df_year     = an.production_by_year(df)
    df_lc       = an.life_cycle(df)
    df_acpy     = an.avg_citations_per_year(df)
    df_src      = an.top_sources(df)
    bradford    = an.bradford_law(df)
    df_src_time = an.sources_production_over_time(df)
    df_auth     = an.top_authors(df)
    df_lotka    = an.lotka_law(df)
    df_auth_t   = an.authors_production_over_time(df)
    df_aff      = an.top_affiliations(df)
    df_co       = an.top_countries(df)
    df_co_time  = an.countries_production_over_time(df)
    df_cit      = an.citation_summary(df)
    df_types    = an.document_types(df)
    df_oa       = an.open_access_breakdown(df)
    df_pub      = an.publisher_concentration(df)
    df_kw       = an.top_keywords(df)
    df_wot      = an.words_frequency_over_time(df)
    df_trend    = an.trend_topics(df)
    df_growth   = an.keyword_growth_rate(df)
    df_tfidf    = an.abstract_tfidf(df)
    df_age      = an.citation_age_distribution(df)
    df_tm       = an.thematic_map(df)
    sankey_data = an.three_field_data(df)

    # ── gráficos ───────────────────────────────────────────────────────────
    h_year       = viz.plot_production_by_year(df_year)
    h_lc         = viz.plot_life_cycle(df_lc)
    h_acpy       = viz.plot_avg_citations_per_year(df_acpy)
    h_src        = viz.plot_top_sources(df_src)
    h_bradford   = viz.plot_bradford(bradford)
    h_src_time   = viz.plot_sources_over_time(df_src_time)
    h_auth       = viz.plot_top_authors(df_auth)
    h_lotka      = viz.plot_lotka(df_lotka)
    h_auth_t     = viz.plot_authors_over_time(df_auth_t)
    h_aff        = viz.plot_top_affiliations(df_aff)
    h_map        = viz.plot_top_countries(df_co)
    h_co_time    = viz.plot_countries_over_time(df_co_time)
    h_cit        = viz.plot_citations_rank(df_cit)
    h_types      = viz.plot_doc_types(df_types)
    h_oa         = viz.plot_open_access(df_oa)
    h_pub        = viz.plot_publisher_concentration(df_pub)
    h_kw         = viz.plot_top_keywords(df_kw)
    h_wcloud     = viz.plot_wordcloud(df_kw)
    h_wot        = viz.plot_words_over_time(df_wot)
    h_trend      = viz.plot_trend_topics(df_trend)
    h_growth     = viz.plot_keyword_growth(df_growth)
    h_sankey     = viz.plot_three_field(sankey_data)
    h_tm         = viz.plot_thematic_map(df_tm)
    h_tfidf      = viz.plot_abstract_tfidf(df_tfidf)
    h_age        = viz.plot_citation_age(df_age)

    # ── redes ──────────────────────────────────────────────────────────────
    G_coauth  = an.coauthorship_network(df, min_papers=1)
    G_kw_net  = an.keyword_cooccurrence_network(df, min_freq=2)
    G_cocit   = an.co_citation_network(df)
    G_country = an.country_collaboration_network(df)

    p_coauth  = nets_dir / "coauthorship.html"
    p_kw      = nets_dir / "keywords.html"
    p_cocit   = nets_dir / "cocitation.html"
    p_country = nets_dir / "countries.html"

    viz.network_to_pyvis_html(G_coauth,  "Co-autoria",    p_coauth,  node_attr="papers")
    viz.network_to_pyvis_html(G_kw_net,  "Co-ocurrencia", p_kw,      node_attr="freq")
    viz.network_to_pyvis_html(G_cocit,   "Co-citacion",   p_cocit,   node_attr="cited")
    viz.network_to_pyvis_html(G_country, "Paises",        p_country, node_attr="papers")

    # ── tabla más citados ──────────────────────────────────────────────────
    df_cit_table = df_cit[["title", "authors", "year", "journal", "cited_by"]].copy()
    df_cit_table["authors"] = df_cit_table["authors"].apply(
        lambda x: ", ".join(x[:2]) + (" et al." if len(x) > 2 else "") if isinstance(x, list) else x
    )

    sources_badge = " · ".join(stats["sources"])

    # ── ensamblar HTML ─────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bibliometrix Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
  {_CSS}
</head>
<body>
{_NAV}
<div class="main">

<div class="hero">
  <h1>Bibliometrix Dashboard</h1>
  <p>Fuentes: {sources_badge} &nbsp;·&nbsp; Periodo: {stats['years_range']}</p>
</div>

<!-- STATS -->
<div class="stats-grid" id="overview">
  {_stat(stats['total_documents'],   'Documentos')}
  {_stat(stats['total_authors'],     'Autores unicos')}
  {_stat(stats['total_sources'],     'Journals')}
  {_stat(stats['total_citations'],   'Citas totales', '#F59E0B')}
  {_stat(stats['avg_citations'],     'Citas promedio', '#10B981')}
  {_stat(stats['h_index'],           'H-index', '#EF4444')}
  {_stat(stats['collaboration_index'], 'Indice colaboracion', '#8B5CF6')}
  {_stat(f"{stats['open_access_pct']}%", 'Open Access', '#10B981')}
</div>

{_divider("PRODUCCION")}
<div class="two-col">
  {_section("produccion-anual", "Produccion por ano", h_year, "Produccion")}
  {_section("ciclo-vida",       "Ciclo de vida",      h_lc,   "Produccion")}
</div>
{_section("citas-por-ano", "Promedio de citas por ano", h_acpy, "Citas")}

{_divider("FUENTES")}
{_section("top-journals",   "Top journals",              h_src,      "Fuentes")}
{_section("bradford",       "Ley de Bradford",           h_bradford, "Ley bibliometrica")}
{_section("journals-tiempo","Journals en el tiempo",     h_src_time, "Dinamica")}

{_divider("AUTORES")}
<div class="two-col">
  {_section("top-autores", "Autores mas productivos", h_auth,  "Autores")}
  {_section("lotka",       "Ley de Lotka",            h_lotka, "Ley bibliometrica")}
</div>
{_section("autores-tiempo", "Produccion de autores en el tiempo", h_auth_t, "Dinamica")}
{_section("afiliaciones",   "Afiliaciones mas frecuentes",        h_aff,    "Afiliaciones")}

{_divider("PAISES")}
{_section("mapa",         "Mapa de produccion mundial", h_map,     "Paises")}
{_section("paises-tiempo","Paises en el tiempo",        h_co_time, "Dinamica")}

{_divider("DOCUMENTOS")}
{_section("mas-citados", "Articulos mas citados (grafico)", h_cit,  "Citas")}
{_section("tabla-citados", "Tabla: articulos mas citados",  _table(df_cit_table), "Tabla")}
<div class="two-col">
  {_section("tipos-doc",   "Tipos de documento", h_types, "Documentos")}
  {_section("open-access", "Open Access",        h_oa,    "OA", new=True)}
</div>
{_section("publishers", "Concentracion de publishers", h_pub, "Publishers", new=True)}

{_divider("KEYWORDS")}
{_section("treemap",        "TreeMap de keywords",           h_kw,     "Keywords")}
{_section("wordcloud",      "Word Cloud",                    h_wcloud, "Keywords")}
{_section("keywords-tiempo","Keywords en el tiempo",         h_wot,    "Dinamica")}
{_section("trend-topics",   "Trend Topics",                  h_trend,  "Tendencias")}
{_section("keyword-growth", "Tasa de crecimiento (CAGR)",    h_growth, "Tendencias", new=True)}

{_divider("SYNTHESIS")}
{_section("sankey",       "Three-Field Plot (Paises - Keywords - Journals)", h_sankey, "Sankey")}
{_section("mapa-tematico","Mapa Tematico",                                   h_tm,     "Conceptual")}
{_section("abstracts",    "Terminos relevantes en abstracts (TF-IDF)",       h_tfidf,  "Texto", new=True)}
{_section("edad-citas",   "Edad de las publicaciones",                       h_age,    "Cronologia", new=True)}

{_divider("REDES")}
{_section("red-coautoria",    "Red de co-autoria",               _iframe(p_coauth,  p_coauth.exists()  and G_coauth.number_of_nodes() > 0),  "Red")}
{_section("red-coocurrencia", "Red de co-ocurrencia de keywords",_iframe(p_kw,      p_kw.exists()      and G_kw_net.number_of_nodes() > 0),  "Red")}
{_section("red-cocitacion",   "Red de co-citacion",              _iframe(p_cocit,   p_cocit.exists()   and G_cocit.number_of_nodes() > 0),   "Red", new=True)}
{_section("red-paises",       "Red de colaboracion entre paises",_iframe(p_country, p_country.exists() and G_country.number_of_nodes() > 0), "Red", new=True)}

</div>
<footer>Generado con Bibliometrix-Py &nbsp;·&nbsp; {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</footer>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"Dashboard guardado en: {output_path.resolve()}")
    return output_path
