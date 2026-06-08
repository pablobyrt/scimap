"""
Métricas bibliométricas completas.
"""
from collections import Counter
from itertools import combinations
import re
import math
import pandas as pd
import numpy as np
import networkx as nx


# ── helpers ───────────────────────────────────────────────────────────────────

def _explode_col(df, col):
    """Expande una columna de listas en filas individuales con el año."""
    rows = []
    for _, r in df.iterrows():
        for item in (r[col] if isinstance(r[col], list) else []):
            rows.append({"year": r["year"], "item": item})
    return pd.DataFrame(rows)


# ── estadísticas generales ────────────────────────────────────────────────────

def summary_stats(df: pd.DataFrame) -> dict:
    all_authors = {a for auths in df["authors"] for a in auths}
    cited = df["cited_by"].fillna(0)
    return {
        "total_documents": len(df),
        "total_authors": len(all_authors),
        "total_sources": df["journal"].nunique(),
        "years_range": f"{int(df['year'].min())} – {int(df['year'].max())}" if df["year"].notna().any() else "N/A",
        "total_citations": int(cited.sum()),
        "avg_citations": round(cited.mean(), 2),
        "h_index": h_index(df),
        "collaboration_index": round(df["author_count"].mean(), 2),
        "open_access_pct": _oa_pct(df),
        "sources": list(df["source"].unique()),
    }


def _oa_pct(df):
    oa = df["note"].str.contains("Open Access", case=False, na=False).sum() if "note" in df.columns else 0
    return round(100 * oa / len(df), 1) if len(df) else 0


def h_index(df: pd.DataFrame) -> int:
    citations = sorted(df["cited_by"].fillna(0), reverse=True)
    h = 0
    for i, c in enumerate(citations, 1):
        if c >= i:
            h = i
        else:
            break
    return h


# ── producción ────────────────────────────────────────────────────────────────

def production_by_year(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.dropna(subset=["year"])
        .groupby("year").size()
        .reset_index(name="count")
        .sort_values("year")
    )


def life_cycle(df: pd.DataFrame) -> pd.DataFrame:
    prod = production_by_year(df)
    prod["cumulative"] = prod["count"].cumsum()
    return prod


def avg_citations_per_year(df: pd.DataFrame, current_year: int = 2026) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        age = current_year - r["year"] if r["year"] and r["year"] <= current_year else None
        if age and age > 0:
            rows.append({"year": r["year"], "acpy": r["cited_by"] / age})
    return (
        pd.DataFrame(rows)
        .groupby("year")["acpy"]
        .mean().round(2)
        .reset_index()
        .sort_values("year")
    )


# ── fuentes ───────────────────────────────────────────────────────────────────

def top_sources(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    vc = df["journal"].value_counts().head(n).reset_index()
    vc.columns = ["journal", "count"]
    return vc


def bradford_law(df: pd.DataFrame) -> dict:
    """Ley de Bradford: distribucion de journals por zonas."""
    jcount = df["journal"].value_counts().reset_index()
    jcount.columns = ["journal", "count"]
    jcount = jcount.sort_values("count", ascending=False).reset_index(drop=True)
    jcount["rank"] = range(1, len(jcount) + 1)
    jcount["cumulative"] = jcount["count"].cumsum()
    total = jcount["count"].sum()
    zone_size = total / 3

    zones = []
    current_zone = 1
    cumulative = 0
    for _, row in jcount.iterrows():
        cumulative += row["count"]
        if cumulative > zone_size * current_zone and current_zone < 3:
            current_zone += 1
        zones.append(current_zone)
    jcount["zone"] = zones

    zone_summary = jcount.groupby("zone").agg(
        journals=("journal", "count"),
        papers=("count", "sum")
    ).reset_index()

    return {"detail": jcount, "summary": zone_summary}


def sources_production_over_time(df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    top = top_sources(df, top_n)["journal"].tolist()
    sub = df[df["journal"].isin(top)].dropna(subset=["year"])
    return sub.groupby(["year", "journal"]).size().reset_index(name="count")


# ── autores ───────────────────────────────────────────────────────────────────

def top_authors(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    counts = Counter(a for auths in df["authors"] for a in auths)
    return pd.DataFrame(counts.most_common(n), columns=["author", "count"])


def lotka_law(df: pd.DataFrame) -> pd.DataFrame:
    """Ley de Lotka: distribución de productividad de autores."""
    counts = Counter(a for auths in df["authors"] for a in auths)
    freq = Counter(counts.values())
    result = pd.DataFrame(sorted(freq.items()), columns=["papers", "authors"])
    total_authors = result["authors"].sum()
    # Lotka teórico: f(x) = C / x^2, C = pi^2/6 normalizado
    c = result.loc[result["papers"] == 1, "authors"].values
    c = c[0] if len(c) else total_authors
    result["expected"] = (c / result["papers"] ** 2).round(1)
    return result


def authors_production_over_time(df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    top = top_authors(df, top_n)["author"].tolist()
    rows = []
    for _, r in df.dropna(subset=["year"]).iterrows():
        for a in r["authors"]:
            if a in top:
                rows.append({"year": r["year"], "author": a})
    return pd.DataFrame(rows).groupby(["year", "author"]).size().reset_index(name="count")


def top_affiliations(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    aff_list = []
    for aff in df["affiliations"].dropna():
        parts = re.split(r"[;|]", aff)
        for p in parts:
            p = p.strip()
            if len(p) > 5:
                aff_list.append(p)
    counts = Counter(aff_list)
    return pd.DataFrame(counts.most_common(n), columns=["affiliation", "count"])


# ── países ────────────────────────────────────────────────────────────────────

def top_countries(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    counts = Counter(c for countries in df["countries"] for c in countries)
    return pd.DataFrame(counts.most_common(n), columns=["country", "count"])


def countries_production_over_time(df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    top = top_countries(df, top_n)["country"].tolist()
    rows = []
    for _, r in df.dropna(subset=["year"]).iterrows():
        for c in r["countries"]:
            if c in top:
                rows.append({"year": r["year"], "country": c})
    return pd.DataFrame(rows).groupby(["year", "country"]).size().reset_index(name="count")


def country_collaboration_network(df: pd.DataFrame) -> nx.Graph:
    G = nx.Graph()
    for _, r in df.iterrows():
        countries = list(set(r["countries"]))
        for c in countries:
            G.add_node(c)
        for c1, c2 in combinations(countries, 2):
            if G.has_edge(c1, c2):
                G[c1][c2]["weight"] += 1
            else:
                G.add_edge(c1, c2, weight=1)
    return G


# ── documentos ────────────────────────────────────────────────────────────────

def citation_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df[["title", "authors", "year", "journal", "cited_by"]]
        .sort_values("cited_by", ascending=False)
        .head(20).reset_index(drop=True)
    )


def document_types(df: pd.DataFrame) -> pd.DataFrame:
    vc = df["type"].value_counts().reset_index()
    vc.columns = ["type", "count"]
    return vc


def language_distribution(df: pd.DataFrame) -> pd.DataFrame:
    vc = df["language"].value_counts().reset_index()
    vc.columns = ["language", "count"]
    return vc


# ── keywords ──────────────────────────────────────────────────────────────────

def top_keywords(df: pd.DataFrame, n: int = 30) -> pd.DataFrame:
    counts = Counter(
        kw.lower() for kws in df["keywords"] for kw in kws if len(kw) > 2
    )
    return pd.DataFrame(counts.most_common(n), columns=["keyword", "count"])


def words_frequency_over_time(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    top_kws = top_keywords(df, top_n)["keyword"].tolist()
    rows = []
    for _, r in df.dropna(subset=["year"]).iterrows():
        kws = {kw.lower() for kw in r["keywords"]}
        for kw in kws:
            if kw in top_kws:
                rows.append({"year": r["year"], "keyword": kw})
    if not rows:
        return pd.DataFrame(columns=["year", "keyword", "count"])
    return (
        pd.DataFrame(rows)
        .groupby(["year", "keyword"]).size()
        .reset_index(name="count")
        .sort_values("year")
    )


def trend_topics(df: pd.DataFrame, n_periods: int = 3, top_n: int = 10) -> pd.DataFrame:
    """Keywords con mayor crecimiento entre el primer y último período."""
    df2 = df.dropna(subset=["year"]).copy()
    if df2.empty:
        return pd.DataFrame()
    min_y, max_y = int(df2["year"].min()), int(df2["year"].max())
    span = max_y - min_y
    if span == 0:
        return pd.DataFrame()
    period_size = span / n_periods

    def get_period(y):
        p = int((y - min_y) / period_size)
        return min(p, n_periods - 1)

    df2["period"] = df2["year"].apply(get_period)
    rows = []
    for _, r in df2.iterrows():
        for kw in r["keywords"]:
            rows.append({"period": r["period"], "keyword": kw.lower()})
    if not rows:
        return pd.DataFrame()

    kw_df = pd.DataFrame(rows)
    pivot = kw_df.groupby(["period", "keyword"]).size().unstack(fill_value=0)
    pivot = pivot.T
    pivot.columns = [f"P{i+1}" for i in pivot.columns]

    # Crecimiento = último - primero período
    first_col, last_col = pivot.columns[0], pivot.columns[-1]
    pivot["growth"] = pivot[last_col] - pivot[first_col]
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot[pivot["total"] >= 2]  # mínimo 2 apariciones

    result = pivot.sort_values("growth", ascending=False).head(top_n).reset_index()
    result = result.rename(columns={"keyword": "keyword"})
    return result


# ── redes ─────────────────────────────────────────────────────────────────────

def coauthorship_network(df: pd.DataFrame, min_papers: int = 1) -> nx.Graph:
    G = nx.Graph()
    author_counts = Counter(a for auths in df["authors"] for a in auths)
    for _, row in df.iterrows():
        authors = [a for a in row["authors"] if author_counts[a] >= min_papers]
        for i, a1 in enumerate(authors):
            G.add_node(a1, papers=author_counts[a1])
            for a2 in authors[i + 1:]:
                if G.has_edge(a1, a2):
                    G[a1][a2]["weight"] += 1
                else:
                    G.add_edge(a1, a2, weight=1)
    return G


def keyword_cooccurrence_network(df: pd.DataFrame, min_freq: int = 2) -> nx.Graph:
    G = nx.Graph()
    freq = Counter(kw.lower() for kws in df["keywords"] for kw in kws if len(kw) > 2)
    for _, row in df.iterrows():
        kws = list({kw.lower() for kw in row["keywords"] if freq[kw.lower()] >= min_freq})
        for i, k1 in enumerate(kws):
            G.add_node(k1, freq=freq[k1])
            for k2 in kws[i + 1:]:
                if G.has_edge(k1, k2):
                    G[k1][k2]["weight"] += 1
                else:
                    G.add_edge(k1, k2, weight=1)
    return G


def thematic_map(df: pd.DataFrame, min_freq: int = 2) -> pd.DataFrame:
    """
    Mapa temático: clusters de keywords en cuadrantes
    (centrality vs density) — Motor, Niche, Emerging, Basic.
    """
    G = keyword_cooccurrence_network(df, min_freq=min_freq)
    if G.number_of_nodes() < 4:
        return pd.DataFrame()

    try:
        from networkx.algorithms.community import greedy_modularity_communities
        communities = list(greedy_modularity_communities(G))
    except Exception:
        return pd.DataFrame()

    centrality = nx.degree_centrality(G)
    rows = []
    for i, comm in enumerate(communities):
        if len(comm) < 2:
            continue
        sub = G.subgraph(comm)
        # Densidad interna
        density = nx.density(sub)
        # Centralidad = media de centralidades de los nodos del cluster en el grafo global
        cent = np.mean([centrality[n] for n in comm])
        # Label = keyword más central del cluster
        top_node = max(comm, key=lambda n: centrality[n])
        rows.append({
            "cluster": i + 1,
            "label": top_node,
            "keywords": ", ".join(sorted(comm)[:5]),
            "centrality": round(cent, 4),
            "density": round(density, 4),
            "size": len(comm),
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    med_cent = result["centrality"].median()
    med_dens = result["density"].median()

    def quadrant(row):
        if row["centrality"] >= med_cent and row["density"] >= med_dens:
            return "Motor themes"
        elif row["centrality"] < med_cent and row["density"] >= med_dens:
            return "Niche themes"
        elif row["centrality"] >= med_cent and row["density"] < med_dens:
            return "Basic themes"
        else:
            return "Emerging themes"

    result["quadrant"] = result.apply(quadrant, axis=1)
    return result


def co_citation_network(df: pd.DataFrame) -> nx.Graph:
    """
    Red de co-citación basada en keywords compartidas
    (proxy cuando no hay referencias completas).
    """
    G = nx.Graph()
    for _, r in df.iterrows():
        nid = r.get("id") or r["title"][:40]
        G.add_node(nid, title=r["title"][:60], year=r["year"], cited=r["cited_by"])

    doc_list = list(df.iterrows())
    for i in range(len(doc_list)):
        _, r1 = doc_list[i]
        kws1 = set(kw.lower() for kw in r1["keywords"])
        id1 = r1.get("id") or r1["title"][:40]
        for j in range(i + 1, len(doc_list)):
            _, r2 = doc_list[j]
            kws2 = set(kw.lower() for kw in r2["keywords"])
            shared = len(kws1 & kws2)
            if shared >= 2:
                id2 = r2.get("id") or r2["title"][:40]
                G.add_edge(id1, id2, weight=shared)
    return G


# ── análisis de texto (abstracts) ─────────────────────────────────────────────

def abstract_tfidf(df: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """TF-IDF simple sobre abstracts para encontrar términos relevantes."""
    import math
    stopwords = {
        "the", "a", "an", "and", "or", "of", "in", "to", "for", "is", "are",
        "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might", "can", "this",
        "that", "these", "those", "with", "from", "by", "on", "at", "as", "it",
        "its", "we", "our", "their", "which", "also", "such", "than", "more",
        "than", "not", "no", "but", "however", "both", "between", "through",
        "into", "over", "about", "based", "using", "used", "use", "show", "shows",
        "shown", "provide", "provides", "approach", "paper", "study", "work",
        "results", "method", "methods", "present", "proposed", "new", "high",
        "large", "data", "system", "different", "each", "other", "well", "while",
        "two", "three", "number", "various", "include", "including", "related",
    }

    docs = df["abstract"].dropna().tolist()
    if not docs:
        return pd.DataFrame(columns=["term", "tfidf"])

    tokenized = []
    for doc in docs:
        tokens = re.findall(r"\b[a-zA-Z]{4,}\b", doc.lower())
        tokens = [t for t in tokens if t not in stopwords]
        tokenized.append(tokens)

    tf_dicts = [Counter(tokens) for tokens in tokenized]
    N = len(tokenized)
    all_terms = set(t for d in tokenized for t in d)
    df_count = {t: sum(1 for d in tokenized if t in d) for t in all_terms}

    scores = {}
    for term in all_terms:
        idf = math.log(N / (1 + df_count[term]))
        avg_tf = sum(d.get(term, 0) / max(len(tok), 1) for d, tok in zip(tf_dicts, tokenized)) / N
        scores[term] = avg_tf * idf

    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return pd.DataFrame(top, columns=["term", "tfidf"]).round(4)


# ── nuevas métricas sugeridas ─────────────────────────────────────────────────

def open_access_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Distribución de tipos de Open Access."""
    types = {"Gold OA": 0, "Green OA": 0, "Hybrid OA": 0, "Closed": 0}
    note_col = df.get("note", pd.Series(dtype=str)) if "note" not in df.columns else df["note"]
    for note in note_col.fillna(""):
        if "Gold Open Access" in note:
            types["Gold OA"] += 1
        elif "Green Open Access" in note:
            types["Green OA"] += 1
        elif "Hybrid" in note:
            types["Hybrid OA"] += 1
        elif "Open Access" not in note:
            types["Closed"] += 1
    return pd.DataFrame(list(types.items()), columns=["type", "count"])


def publisher_concentration(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    vc = df["publisher"].value_counts().head(n).reset_index()
    vc.columns = ["publisher", "count"]
    vc["pct"] = (100 * vc["count"] / len(df)).round(1)
    return vc


def keyword_growth_rate(df: pd.DataFrame, min_total: int = 2) -> pd.DataFrame:
    """CAGR de keywords entre primer y último año con datos."""
    df2 = df.dropna(subset=["year"]).copy()
    if df2.empty:
        return pd.DataFrame()
    min_y, max_y = int(df2["year"].min()), int(df2["year"].max())
    span = max_y - min_y
    if span == 0:
        return pd.DataFrame()

    rows = []
    for _, r in df2.iterrows():
        for kw in r["keywords"]:
            rows.append({"year": int(r["year"]), "keyword": kw.lower()})

    kw_df = pd.DataFrame(rows)
    pivot = kw_df.groupby(["year", "keyword"]).size().unstack(fill_value=0)

    results = []
    for kw in pivot.columns:
        total = pivot[kw].sum()
        if total < min_total:
            continue
        first_val = pivot[kw].iloc[0] + 0.5
        last_val = pivot[kw].iloc[-1] + 0.5
        cagr = (last_val / first_val) ** (1 / span) - 1
        results.append({"keyword": kw, "total": int(total), "cagr": round(cagr * 100, 1)})

    return pd.DataFrame(results).sort_values("cagr", ascending=False).reset_index(drop=True)


def citation_age_distribution(df: pd.DataFrame, current_year: int = 2026) -> pd.DataFrame:
    """Distribución de la 'edad' de las publicaciones al momento de ser citadas."""
    ages = (current_year - df["year"].dropna()).astype(int)
    counts = ages.value_counts().sort_index().reset_index()
    counts.columns = ["age_years", "count"]
    return counts[counts["age_years"] >= 0]


def three_field_data(
    df: pd.DataFrame,
    field1: str = "countries",
    field2: str = "keywords",
    field3: str = "journal",
    top_n: int = 8,
) -> dict:
    """Datos para el Sankey de tres campos."""

    def get_top(series_of_lists, n):
        c = Counter(item for lst in series_of_lists for item in (lst if isinstance(lst, list) else [lst]))
        return [x for x, _ in c.most_common(n)]

    top1 = get_top(df[field1], top_n)
    top2 = get_top(df[field2], top_n)
    top3 = df[field3].value_counts().head(top_n).index.tolist()

    links_12, links_23 = Counter(), Counter()
    for _, r in df.iterrows():
        f1_vals = [v for v in (r[field1] if isinstance(r[field1], list) else [r[field1]]) if v in top1]
        f2_vals = [v.lower() for v in (r[field2] if isinstance(r[field2], list) else [r[field2]]) if v.lower() in [t.lower() for t in top2]]
        f3_val = r[field3] if r[field3] in top3 else None

        for v1 in f1_vals:
            for v2 in f2_vals:
                links_12[(v1, v2)] += 1
        if f3_val:
            for v2 in f2_vals:
                links_23[(v2, f3_val)] += 1

    labels = list(set(top1 + top2 + top3))
    label_idx = {l: i for i, l in enumerate(labels)}

    sources, targets, values = [], [], []
    for (s, t), v in links_12.items():
        if s in label_idx and t in label_idx:
            sources.append(label_idx[s])
            targets.append(label_idx[t])
            values.append(v)
    for (s, t), v in links_23.items():
        if s in label_idx and t in label_idx:
            sources.append(label_idx[s])
            targets.append(label_idx[t])
            values.append(v)

    return {"labels": labels, "sources": sources, "targets": targets, "values": values}
