"""
Genera figuras Plotly y redes pyvis.
"""
import json
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx
import pandas as pd

PALETTE = px.colors.qualitative.Plotly
ACCENT = "#2563EB"
BG = "white"


def _fig(fig: go.Figure, title: str = "", height: int = 0) -> go.Figure:
    layout = dict(plot_bgcolor=BG, paper_bgcolor=BG, margin=dict(t=50, b=30, l=10, r=10))
    if height:
        layout["height"] = height
    if title:
        layout["title"] = title
    fig.update_layout(**layout)
    return fig


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})


# ── producción ────────────────────────────────────────────────────────────────

def plot_production_by_year(df_year: pd.DataFrame) -> str:
    fig = go.Figure(go.Bar(
        x=df_year["year"], y=df_year["count"],
        marker_color=ACCENT, text=df_year["count"], textposition="outside",
    ))
    return _html(_fig(fig, "Produccion cientifica por ano", 380))


def plot_life_cycle(df_lc: pd.DataFrame) -> str:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_lc["year"], y=df_lc["count"],
                         name="Anual", marker_color="#93C5FD", opacity=0.7))
    fig.add_trace(go.Scatter(x=df_lc["year"], y=df_lc["cumulative"],
                             name="Acumulado", line=dict(color=ACCENT, width=3),
                             yaxis="y2"))
    fig.update_layout(
        title="Ciclo de vida de la produccion",
        yaxis=dict(title="Publicaciones anuales"),
        yaxis2=dict(title="Acumulado", overlaying="y", side="right"),
        plot_bgcolor=BG, paper_bgcolor=BG,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=380,
    )
    return _html(fig)


def plot_avg_citations_per_year(df: pd.DataFrame) -> str:
    fig = go.Figure(go.Scatter(
        x=df["year"], y=df["acpy"],
        mode="lines+markers", line=dict(color="#10B981", width=3),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.1)",
        text=df["acpy"], hovertemplate="%{x}: %{y:.2f} cit/año",
    ))
    return _html(_fig(fig, "Promedio de citas por ano de publicacion", 360))


# ── fuentes ───────────────────────────────────────────────────────────────────

def plot_top_sources(df_src: pd.DataFrame) -> str:
    df_src = df_src.sort_values("count")
    df_src["journal_short"] = df_src["journal"].apply(lambda x: x[:50] + "..." if len(x) > 50 else x)
    fig = go.Figure(go.Bar(
        x=df_src["count"], y=df_src["journal_short"],
        orientation="h", marker_color=ACCENT,
        text=df_src["count"], textposition="outside",
    ))
    return _html(_fig(fig, "Top journals / fuentes", max(350, len(df_src) * 30)))


def plot_bradford(data: dict) -> str:
    detail = data["detail"]
    colors = {"1": "#2563EB", "2": "#10B981", "3": "#F59E0B"}
    zone_colors = [colors.get(str(z), "#94A3B8") for z in detail["zone"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=detail["rank"], y=detail["count"],
        marker_color=zone_colors,
        hovertemplate="<b>%{customdata}</b><br>Rank: %{x}<br>Papers: %{y}",
        customdata=detail["journal"],
    ))
    summary = data["summary"]
    for _, row in summary.iterrows():
        z = int(row["zone"])
        fig.add_annotation(
            text=f"Zona {z}<br>{int(row['journals'])} journals<br>{int(row['papers'])} papers",
            xref="paper", yref="paper",
            x=0.02 + (z - 1) * 0.33, y=0.97, showarrow=False,
            bgcolor=list(colors.values())[z - 1], opacity=0.8,
            font=dict(color="white", size=10), align="center",
        )
    return _html(_fig(fig, "Ley de Bradford — Distribucion de journals", 420))


def plot_sources_over_time(df: pd.DataFrame) -> str:
    fig = px.line(df, x="year", y="count", color="journal",
                  markers=True, title="Produccion de journals en el tiempo")
    fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=400,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.4))
    return _html(fig)


# ── autores ───────────────────────────────────────────────────────────────────

def plot_top_authors(df_auth: pd.DataFrame) -> str:
    df_auth = df_auth.sort_values("count")
    fig = go.Figure(go.Bar(
        x=df_auth["count"], y=df_auth["author"],
        orientation="h", marker_color="#10B981",
        text=df_auth["count"], textposition="outside",
    ))
    return _html(_fig(fig, "Autores mas productivos", max(350, len(df_auth) * 28)))


def plot_lotka(df_lotka: pd.DataFrame) -> str:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_lotka["papers"], y=df_lotka["authors"],
                         name="Observado", marker_color=ACCENT, opacity=0.8))
    fig.add_trace(go.Scatter(x=df_lotka["papers"], y=df_lotka["expected"],
                             name="Esperado (Lotka)", mode="lines+markers",
                             line=dict(color="#EF4444", width=2, dash="dash")))
    fig.update_layout(
        title="Ley de Lotka — Productividad de autores",
        xaxis_title="Numero de publicaciones", yaxis_title="Numero de autores",
        plot_bgcolor=BG, paper_bgcolor=BG, height=380,
    )
    return _html(fig)


def plot_authors_over_time(df: pd.DataFrame) -> str:
    fig = px.line(df, x="year", y="count", color="author",
                  markers=True, title="Produccion de autores en el tiempo")
    fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=400,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.4))
    return _html(fig)


def plot_top_affiliations(df: pd.DataFrame) -> str:
    df = df.sort_values("count")
    df["aff_short"] = df["affiliation"].apply(lambda x: x[:55] + "..." if len(x) > 55 else x)
    fig = go.Figure(go.Bar(
        x=df["count"], y=df["aff_short"],
        orientation="h", marker_color="#8B5CF6",
        text=df["count"], textposition="outside",
    ))
    return _html(_fig(fig, "Afiliaciones mas frecuentes", max(350, len(df) * 28)))


# ── países ────────────────────────────────────────────────────────────────────

def plot_top_countries(df_co: pd.DataFrame) -> str:
    fig = go.Figure(go.Choropleth(
        locations=df_co["country"], locationmode="country names",
        z=df_co["count"], colorscale="Blues", colorbar_title="Publicaciones",
    ))
    fig.update_layout(
        title="Mapa de produccion cientifica",
        geo=dict(showframe=False, showcoastlines=True),
        margin=dict(l=0, r=0, t=50, b=0), height=420,
    )
    return _html(fig)


def plot_countries_over_time(df: pd.DataFrame) -> str:
    fig = px.line(df, x="year", y="count", color="country",
                  markers=True, title="Produccion de paises en el tiempo")
    fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=400,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.4))
    return _html(fig)


# ── keywords ──────────────────────────────────────────────────────────────────

def plot_top_keywords(df_kw: pd.DataFrame) -> str:
    fig = px.treemap(df_kw, path=["keyword"], values="count",
                     color="count", color_continuous_scale="Blues",
                     title="Palabras clave — TreeMap")
    fig.update_traces(textinfo="label+value")
    fig.update_layout(margin=dict(t=50, l=0, r=0, b=0))
    return _html(fig)


def plot_wordcloud(df_kw: pd.DataFrame) -> str:
    """WordCloud como scatter de texto con tamaño proporcional."""
    if df_kw.empty:
        return "<p>Sin datos.</p>"
    max_c = df_kw["count"].max()
    np.random.seed(42)
    x = np.random.uniform(0, 10, len(df_kw))
    y = np.random.uniform(0, 10, len(df_kw))
    sizes = 10 + 40 * (df_kw["count"] / max_c)
    colors = df_kw["count"].tolist()

    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="text",
        text=df_kw["keyword"],
        textfont=dict(size=sizes.tolist(), color=[
            f"rgb({int(30 + 200*(1-c/max_c))},{int(80 + 100*(c/max_c))},{int(220*(c/max_c))})"
            for c in df_kw["count"]
        ]),
        hovertext=[f"{kw}: {cnt}" for kw, cnt in zip(df_kw["keyword"], df_kw["count"])],
        hoverinfo="text",
    ))
    fig.update_layout(
        title="Word Cloud de keywords",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="#F8FAFC", paper_bgcolor=BG, height=420,
    )
    return _html(fig)


def plot_words_over_time(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>Sin datos suficientes.</p>"
    pivot = df.pivot_table(index="year", columns="keyword", values="count", fill_value=0)
    fig = go.Figure()
    for col in pivot.columns:
        fig.add_trace(go.Scatter(x=pivot.index, y=pivot[col], name=col,
                                 mode="lines+markers"))
    fig.update_layout(
        title="Frecuencia de keywords en el tiempo",
        plot_bgcolor=BG, paper_bgcolor=BG, height=420,
        legend=dict(orientation="h", yanchor="bottom", y=-0.5),
    )
    return _html(fig)


def plot_trend_topics(df_trend: pd.DataFrame) -> str:
    if df_trend.empty:
        return "<p>Sin datos suficientes para trend topics (se necesitan al menos 2 anos).</p>"
    period_cols = [c for c in df_trend.columns if c.startswith("P")]
    fig = go.Figure()
    for _, row in df_trend.iterrows():
        values = [row[c] for c in period_cols]
        growth = row.get("growth", 0)
        color = "#10B981" if growth > 0 else "#EF4444"
        fig.add_trace(go.Scatter(
            x=period_cols, y=values, name=row["keyword"],
            mode="lines+markers+text", text=[None] * (len(period_cols)-1) + [row["keyword"]],
            textposition="middle right", line=dict(color=color, width=2),
        ))
    fig.update_layout(
        title="Trend Topics — Evolucion de keywords por periodo",
        plot_bgcolor=BG, paper_bgcolor=BG, height=480,
        showlegend=False,
        xaxis_title="Periodo",
        yaxis_title="Frecuencia",
    )
    return _html(fig)


def plot_thematic_map(df_tm: pd.DataFrame) -> str:
    if df_tm.empty:
        return "<p>Sin datos suficientes para el mapa tematico (se necesitan mas documentos y keywords repetidas).</p>"

    q_colors = {
        "Motor themes": "#2563EB",
        "Niche themes": "#10B981",
        "Basic themes": "#F59E0B",
        "Emerging themes": "#EF4444",
    }

    fig = go.Figure()
    for q, color in q_colors.items():
        sub = df_tm[df_tm["quadrant"] == q]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["centrality"], y=sub["density"],
            mode="markers+text", name=q,
            text=sub["label"], textposition="top center",
            marker=dict(size=sub["size"] * 6 + 10, color=color, opacity=0.75,
                        line=dict(width=1, color="white")),
            hovertext=sub["keywords"],
        ))

    med_x = df_tm["centrality"].median()
    med_y = df_tm["density"].median()
    fig.add_hline(y=med_y, line_dash="dot", line_color="#94A3B8")
    fig.add_vline(x=med_x, line_dash="dot", line_color="#94A3B8")

    for q, (xa, ya) in {
        "Motor themes": (1.02, 1.02),
        "Niche themes": (-0.02, 1.02),
        "Basic themes": (1.02, -0.02),
        "Emerging themes": (-0.02, -0.02),
    }.items():
        fig.add_annotation(
            x=xa, y=ya, xref="paper", yref="paper",
            text=q, showarrow=False, font=dict(size=10, color=q_colors[q]),
            bgcolor="white", bordercolor=q_colors[q],
        )

    fig.update_layout(
        title="Mapa Tematico — Centralidad vs Densidad",
        xaxis_title="Centrality (importancia externa)",
        yaxis_title="Density (cohesion interna)",
        plot_bgcolor="#F8FAFC", paper_bgcolor=BG,
        height=520, legend=dict(orientation="h", y=-0.15),
    )
    return _html(fig)


# ── documentos ────────────────────────────────────────────────────────────────

def plot_citations_rank(df_cit: pd.DataFrame) -> str:
    df_cit = df_cit.head(15).copy()
    df_cit["title_short"] = df_cit["title"].apply(lambda x: x[:60] + "..." if len(x) > 60 else x)
    df_cit = df_cit.sort_values("cited_by")
    fig = go.Figure(go.Bar(
        x=df_cit["cited_by"], y=df_cit["title_short"],
        orientation="h", marker_color="#F59E0B",
        text=df_cit["cited_by"], textposition="outside",
    ))
    return _html(_fig(fig, "Articulos mas citados", max(350, len(df_cit) * 35)))


def plot_doc_types(df_types: pd.DataFrame) -> str:
    fig = go.Figure(go.Pie(
        labels=df_types["type"], values=df_types["count"],
        hole=0.4, marker=dict(colors=PALETTE),
    ))
    fig.update_layout(title="Tipos de documento", margin=dict(t=50),
                      paper_bgcolor=BG)
    return _html(fig)


def plot_three_field(data: dict) -> str:
    if not data["sources"]:
        return "<p>Sin datos suficientes para el Sankey.</p>"
    import plotly.graph_objects as go
    fig = go.Figure(go.Sankey(
        node=dict(label=data["labels"], pad=12, thickness=18,
                  color=[PALETTE[i % len(PALETTE)] for i in range(len(data["labels"]))]),
        link=dict(source=data["sources"], target=data["targets"], value=data["values"],
                  color="rgba(37,99,235,0.2)"),
    ))
    fig.update_layout(title="Three-Field Plot (Paises - Keywords - Journals)",
                      paper_bgcolor=BG, height=500, font_size=11)
    return _html(fig)


# ── nuevas visualizaciones ────────────────────────────────────────────────────

def plot_open_access(df_oa: pd.DataFrame) -> str:
    fig = go.Figure(go.Pie(
        labels=df_oa["type"], values=df_oa["count"],
        hole=0.4, marker=dict(colors=["#10B981", "#3B82F6", "#8B5CF6", "#94A3B8"]),
    ))
    fig.update_layout(title="Distribucion de Open Access", paper_bgcolor=BG,
                      margin=dict(t=50))
    return _html(fig)


def plot_publisher_concentration(df: pd.DataFrame) -> str:
    fig = go.Figure(go.Bar(
        x=df["count"], y=df["publisher"],
        orientation="h", marker_color="#8B5CF6",
        text=[f"{c} ({p}%)" for c, p in zip(df["count"], df["pct"])],
        textposition="outside",
    ))
    return _html(_fig(fig, "Concentracion de publishers", max(300, len(df) * 32)))


def plot_keyword_growth(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>Sin datos (se necesitan al menos 2 anos).</p>"
    top = df.head(20).copy()
    colors = ["#10B981" if g > 0 else "#EF4444" for g in top["cagr"]]
    top = top.sort_values("cagr")
    fig = go.Figure(go.Bar(
        x=top["cagr"], y=top["keyword"],
        orientation="h", marker_color=colors,
        text=[f"{g:+.1f}%" for g in top["cagr"]], textposition="outside",
    ))
    return _html(_fig(fig, "Tasa de crecimiento de keywords (CAGR %)", max(400, len(top) * 30)))


def plot_abstract_tfidf(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>Sin abstracts disponibles.</p>"
    df = df.sort_values("tfidf")
    fig = go.Figure(go.Bar(
        x=df["tfidf"], y=df["term"],
        orientation="h", marker_color="#0EA5E9",
        text=df["tfidf"].round(3), textposition="outside",
    ))
    return _html(_fig(fig, "Terminos mas relevantes en abstracts (TF-IDF)", max(400, len(df) * 28)))


# ── género ────────────────────────────────────────────────────────────────────

GENDER_COLORS = {
    "Masculino":           "#2563EB",
    "Mayorm. masculino":   "#93C5FD",
    "Femenino":            "#EC4899",
    "Mayorm. femenino":    "#F9A8D4",
    "Ambiguo":             "#F59E0B",
    "Desconocido":         "#94A3B8",
}


def plot_gender_overall(data: dict) -> str:
    df = data["overall"]
    colors = [GENDER_COLORS.get(g, "#94A3B8") for g in df["gender"]]
    fig = go.Figure(go.Pie(
        labels=[f"{g} ({p}%)" for g, p in zip(df["gender"], df["pct"])],
        values=df["count"], hole=0.45,
        marker=dict(colors=colors),
        textinfo="label+value",
    ))
    fig.update_layout(
        title="Distribucion de genero — autores unicos",
        paper_bgcolor=BG, margin=dict(t=50, b=10),
        annotations=[dict(text=f"n={df['count'].sum()}", x=0.5, y=0.5,
                          font_size=14, showarrow=False)],
    )
    return _html(fig)


def plot_gender_by_year(data: dict) -> str:
    df = data["by_year"]
    if df.empty:
        return "<p>Sin datos por ano.</p>"
    fig = px.bar(df, x="year", y="count", color="gender",
                 color_discrete_map=GENDER_COLORS,
                 barmode="stack",
                 title="Genero de autores por ano",
                 labels={"count": "Autores", "year": "Ano", "gender": "Genero"})
    fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=380,
                      legend=dict(orientation="h", y=-0.2))
    return _html(fig)


def plot_gender_ratio(data: dict) -> str:
    df = data["ratio"]
    if df.empty:
        return "<p>Sin datos suficientes para calcular el ratio.</p>"
    fig = go.Figure(go.Scatter(
        x=df["year"], y=df["ratio_mf"],
        mode="lines+markers+text",
        text=df["ratio_mf"],
        textposition="top center",
        line=dict(color="#2563EB", width=3),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.1)",
    ))
    fig.add_hline(y=1, line_dash="dot", line_color="#10B981",
                  annotation_text="Paridad (1:1)", annotation_position="right")
    fig.update_layout(
        title="Ratio Masculino / Femenino por ano (>1 = predominio masculino)",
        xaxis_title="Ano", yaxis_title="Ratio M/F",
        plot_bgcolor=BG, paper_bgcolor=BG, height=360,
    )
    return _html(fig)


_CONFIDENCE_LABEL = {
    "male":         ("Alta", "#DCFCE7", "#15803D"),
    "female":       ("Alta", "#DCFCE7", "#15803D"),
    "mostly_male":  ("Media", "#FEF9C3", "#92400E"),
    "mostly_female":("Media", "#FEF9C3", "#92400E"),
    "andy":         ("Ambiguo", "#FEF3C7", "#B45309"),
    "unknown":      ("Sin datos", "#F1F5F9", "#64748B"),
}

_ROW_BG = {
    "Masculino":          "#EFF6FF",
    "Mayorm. masculino":  "#F0F9FF",
    "Femenino":           "#FDF2F8",
    "Mayorm. femenino":   "#FFF0F6",
    "Ambiguo":            "#FFFBEB",
    "Desconocido":        "#F8FAFC",
}


def plot_gender_detail_table(data: dict) -> str:
    df = data["author_detail"].copy()
    rows = ""
    for _, row in df.iterrows():
        conf_label, conf_bg, conf_color = _CONFIDENCE_LABEL.get(
            row["gender_raw"], ("?", "#F8FAFC", "#64748B"))
        bg = _ROW_BG.get(row["gender"], "#F8FAFC")
        gc = GENDER_COLORS.get(row["gender"], "#94A3B8")
        badge = f'<span style="background:{gc};color:white;padding:2px 8px;border-radius:99px;font-size:.75rem">{row["gender"]}</span>'
        conf_badge = f'<span style="background:{conf_bg};color:{conf_color};padding:2px 8px;border-radius:99px;font-size:.75rem">{conf_label}</span>'
        rows += f'<tr style="background:{bg}"><td>{row["author"]}</td><td>{row["first_name"] or "—"}</td><td>{badge}</td><td>{conf_badge}</td></tr>'
    return (
        "<table><thead><tr>"
        "<th>Autor</th><th>Primer nombre</th><th>Genero inferido</th><th>Confianza</th>"
        "</tr></thead><tbody>" + rows + "</tbody></table>"
    )


def plot_citation_age(df: pd.DataFrame) -> str:
    fig = go.Figure(go.Bar(
        x=df["age_years"], y=df["count"],
        marker_color=ACCENT, text=df["count"], textposition="outside",
    ))
    return _html(_fig(fig, "Distribucion de edad de las publicaciones (anos desde publicacion)", 380))


# ── redes ─────────────────────────────────────────────────────────────────────

def network_to_pyvis_html(G: nx.Graph, title: str, output_path: Path,
                           node_attr: str = "papers") -> str:
    try:
        from pyvis.network import Network
    except ImportError:
        return ""
    if G.number_of_nodes() == 0:
        return ""

    if G.number_of_nodes() > 80:
        top_nodes = sorted(G.degree, key=lambda x: x[1], reverse=True)[:80]
        G = G.subgraph([n for n, _ in top_nodes]).copy()

    net = Network(height="520px", width="100%", bgcolor="#F8FAFC", font_color="#1e293b")
    net.set_options(json.dumps({
        "nodes": {"shape": "dot", "scaling": {"min": 8, "max": 28}},
        "edges": {"color": {"opacity": 0.4}, "smooth": False},
        "physics": {
            "stabilization": {
                "iterations": 500,
                "fit": True,
                "updateInterval": 25
            },
            "enabled": False
        },
        "interaction": {"hover": True, "tooltipDelay": 100},
    }))

    vals = [d.get(node_attr, 1) for _, d in G.nodes(data=True)]
    max_val = max(vals) if vals else 1

    for node, data in G.nodes(data=True):
        val = data.get(node_attr, 1)
        net.add_node(node, label=str(node)[:30],
                     size=8 + 20 * (val / max_val),
                     title=f"{node}<br>{node_attr}: {val}")

    for u, v, data in G.edges(data=True):
        net.add_edge(u, v, value=data.get("weight", 1))

    net.save_graph(str(output_path))
    return str(output_path)
