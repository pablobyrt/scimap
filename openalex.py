"""
openalex.py — Cliente OpenAlex para Scimap

Permite buscar papers directamente desde la API sin exportar archivos.
API docs: https://docs.openalex.org
Límite: 100k req/día (polite pool con email)
"""

from __future__ import annotations
import time
import re
from pathlib import Path

import requests
import pandas as pd

API_BASE   = "https://api.openalex.org"
MAILTO     = "scimap@research.app"
PAGE_SIZE  = 200          # máximo por request
MAX_PAGES  = 10           # hasta 2000 results por búsqueda
SLEEP      = 0.12         # pausa entre requests (rate limit)

HEADERS    = {
    "User-Agent": f"SciMap/1.0 (mailto:{MAILTO})",
    "Accept":     "application/json",
}

# ── IDs de conceptos OpenAlex relevantes ──────────────────────────────────────
CONCEPT_IDS = {
    "artificial intelligence": "C119857082",
    "machine learning":        "C154945302",
    "deep learning":           "C108583219",
    "natural language processing": "C204321447",
    "computer vision":         "C31972630",
    "neural network":          "C50644808",
    "data mining":             "C11413529",
    "bibliometrics":           "C178315738",
    "scientometrics":          "C2778793908",
    "information retrieval":   "C126838900",
}

# ── búsqueda de instituciones ─────────────────────────────────────────────────

def search_institutions(query: str, n: int = 8) -> list[dict]:
    """Busca instituciones por nombre. Retorna lista de {id, name, country, works_count}."""
    r = _get("/institutions", {"search": query, "per_page": n, "mailto": MAILTO})
    return [
        {
            "id":          inst["id"].split("/")[-1],     # "I69737025"
            "full_id":     inst["id"],
            "name":        inst["display_name"],
            "country":     inst.get("country_code", ""),
            "works_count": inst.get("works_count", 0),
            "ror":         inst.get("ror", ""),
        }
        for inst in r.get("results", [])
    ]


# ── búsqueda de papers ────────────────────────────────────────────────────────

def fetch_works(
    institution_id: str | None = None,
    keywords: str = "",
    year_from: int = 2020,
    year_to:   int = 2025,
    concept_names: list[str] | None = None,
    doc_types: list[str] | None = None,
    max_results: int = 1000,
    progress_cb=None,
) -> pd.DataFrame:
    """
    Busca papers en OpenAlex y retorna un DataFrame compatible con parser.py.

    Parámetros:
        institution_id  OpenAlex institution ID (ej: "I69737025")
        keywords        Términos de búsqueda libre (busca en título+abstract)
        year_from/to    Rango de años
        concept_names   Lista de conceptos OpenAlex (ej: ["machine learning"])
        doc_types       Tipos: ["article","review","conference-paper",...]
        max_results     Límite de documentos
        progress_cb     Función callback(n_fetched, total) para mostrar progreso
    """
    filters = _build_filters(institution_id, year_from, year_to, concept_names, doc_types)
    params  = {
        "filter":   filters,
        "per_page": PAGE_SIZE,
        "select":   _FIELDS,
        "mailto":   MAILTO,
    }
    if keywords:
        params["search"] = keywords

    records = []
    cursor  = "*"
    total   = None

    for _ in range(MAX_PAGES):
        if len(records) >= max_results:
            break
        params["cursor"] = cursor
        data = _get("/works", params)
        if total is None:
            total = data.get("meta", {}).get("count", 0)

        batch = data.get("results", [])
        if not batch:
            break

        for work in batch:
            if len(records) >= max_results:
                break
            records.append(_parse_work(work))

        if progress_cb:
            progress_cb(len(records), min(total, max_results))

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(SLEEP)

    df = pd.DataFrame(records) if records else pd.DataFrame(columns=_COLUMNS)
    return df


# ── filtros ───────────────────────────────────────────────────────────────────

def _build_filters(inst_id, y_from, y_to, concepts, doc_types):
    parts = [f"publication_year:{y_from}-{y_to}"]

    if inst_id:
        clean = inst_id if inst_id.startswith("I") else f"I{inst_id}"
        parts.append(f"institutions.id:{clean}")

    if concepts:
        concept_ids = []
        for c in concepts:
            c_lower = c.lower().strip()
            if c_lower in CONCEPT_IDS:
                concept_ids.append(CONCEPT_IDS[c_lower])
            elif c.startswith("C") and c[1:].isdigit():
                concept_ids.append(c)
        if concept_ids:
            parts.append("concepts.id:" + "|".join(concept_ids))

    if doc_types:
        parts.append("type:" + "|".join(doc_types))

    return ",".join(parts)


# ── parsear un work ───────────────────────────────────────────────────────────

_FIELDS = (
    "id,doi,title,publication_year,authorships,cited_by_count,"
    "open_access,concepts,primary_location,type,abstract_inverted_index,"
    "biblio,language"
)

_COLUMNS = [
    "id","type","title","year","journal","volume","doi","abstract",
    "authors","author_count","keywords","affiliations","countries",
    "cited_by","language","publisher","source",
    "is_oa","oa_url","openalex_url",
]


def _parse_work(w: dict) -> dict:
    # Autores
    authorships = w.get("authorships") or []
    authors = []
    affiliations_raw = []
    countries = []

    for a in authorships:
        name = (a.get("author") or {}).get("display_name", "")
        if name:
            authors.append(name)
        for inst in (a.get("institutions") or []):
            aff = inst.get("display_name", "")
            if aff:
                affiliations_raw.append(aff)
            country = inst.get("country_code", "")
            if country and country not in countries:
                countries.append(country)

    # Keywords desde conceptos
    concepts = w.get("concepts") or []
    keywords = [
        c["display_name"] for c in concepts
        if c.get("score", 0) >= 0.3
    ][:15]

    # Journal
    loc = w.get("primary_location") or {}
    source = loc.get("source") or {}
    journal = source.get("display_name", "")
    publisher = source.get("host_organization_name", "")

    # Abstract desde inverted index
    abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))

    # OA
    oa = w.get("open_access") or {}
    is_oa  = oa.get("is_oa", False)
    oa_url = oa.get("oa_url", "")

    # Biblio
    biblio = w.get("biblio") or {}

    # Tipo de documento
    doc_type = w.get("type", "article")

    doi = (w.get("doi") or "").replace("https://doi.org/", "")

    # Normalizar afiliaciones
    affiliations_str = " | ".join(affiliations_raw)
    affiliations_norm = normalize_affiliations(affiliations_str)

    return {
        "id":           w.get("id", "").split("/")[-1],
        "type":         doc_type,
        "title":        w.get("title") or "",
        "year":         w.get("publication_year"),
        "journal":      journal,
        "volume":       biblio.get("volume", ""),
        "doi":          doi,
        "abstract":     abstract,
        "authors":      authors,
        "author_count": len(authors),
        "keywords":     keywords,
        "affiliations": affiliations_norm,
        "countries":    countries,
        "cited_by":     w.get("cited_by_count", 0),
        "language":     w.get("language", ""),
        "publisher":    publisher,
        "source":       "OpenAlex",
        "is_oa":        is_oa,
        "oa_url":       oa_url or "",
        "openalex_url": w.get("id", ""),
    }


def _reconstruct_abstract(inv_index: dict | None) -> str:
    if not inv_index:
        return ""
    words: dict[int, str] = {}
    for word, positions in inv_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))


def normalize_affiliations(affiliations_str: str) -> str:
    """
    Homologa variaciones de nombre de instituciones.
    Extrae la institución principal y elimina duplicados.

    Ejemplos:
    - "Universidad de Chile, Santiago, Chile" → "Universidad de Chile"
    - "Instituto de Astronomía, University of Edinburgh, UK" → "University of Edinburgh"
    """
    if not affiliations_str or not isinstance(affiliations_str, str):
        return ""

    # Separar múltiples instituciones (separadas por |)
    affiliations = [aff.strip() for aff in affiliations_str.split("|")]

    normalized = []
    seen = set()

    for aff in affiliations:
        if not aff:
            continue

        # Estrategia 1: Buscar palabras clave de universidad
        inst_name = _extract_main_institution(aff)

        if inst_name and inst_name not in seen:
            normalized.append(inst_name)
            seen.add(inst_name)

    return " | ".join(normalized) if normalized else affiliations_str.split("|")[0].strip()


def _extract_main_institution(aff_text: str) -> str:
    """Extrae el nombre principal de una afiliación."""
    if not aff_text:
        return ""

    # Patrón 1: "Instituto/Department, Universidad, País"
    # Buscar la universidad (última institución antes del país)
    parts = [p.strip() for p in aff_text.split(",")]

    # Palabras clave que indican institución principal
    keywords = [
        "university", "university of", "universidad", "universität", "università",
        "institute", "instituto", "center", "centre", "laboratory", "laboratorio",
        "college", "colegio", "école", "school", "escuela", "politecnico",
    ]

    # Buscar la parte que contiene universidad/institute (típicamente la más importante)
    candidates = []
    for i, part in enumerate(parts):
        part_lower = part.lower()
        # Si contiene palabra clave de institución, es candidato
        if any(kw in part_lower for kw in keywords):
            candidates.append((i, part))

    if candidates:
        # Preferir la institución más importante (generalmente la segunda más importante)
        # Si hay "Instituto de X, Universidad Y", preferimos "Universidad Y"
        idx, main = candidates[-1]  # Última institución con keyword
        return main

    # Si no encontramos keyword, devolver la primera parte (antes de primer comma)
    return parts[0] if parts else aff_text


# ── stats rápidas (para UI preview) ───────────────────────────────────────────

def quick_stats(institution_id: str, year_from: int, year_to: int) -> dict:
    """Retorna conteo rápido sin descargar todos los papers."""
    filters = f"institutions.id:{institution_id},publication_year:{year_from}-{year_to}"
    data = _get("/works", {"filter": filters, "per_page": 1, "mailto": MAILTO})
    return {"total": data.get("meta", {}).get("count", 0)}


def get_top_concepts(institution_id: str, year_from: int, year_to: int, n: int = 20) -> list[dict]:
    """Conceptos/temas más frecuentes de una institución (sin descargar papers)."""
    data = _get(
        f"/institutions/{institution_id}",
        {"select": "x_concepts", "mailto": MAILTO}
    )
    concepts = data.get("x_concepts") or []
    return [
        {"id": c["id"].split("/")[-1], "name": c["display_name"], "score": round(c.get("score", 0), 3)}
        for c in concepts[:n]
    ]


# ── http helper ───────────────────────────────────────────────────────────────

def _get(endpoint: str, params: dict) -> dict:
    url = API_BASE + endpoint
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()
