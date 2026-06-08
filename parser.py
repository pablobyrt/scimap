"""
Parsers para exportaciones de Scopus (.bib) y WoS (.txt).
"""
import re
import html
from pathlib import Path
import pandas as pd


def _clean(val):
    if not isinstance(val, str):
        return val
    return html.unescape(val).strip()


def parse_scopus_bib(path: str | Path) -> pd.DataFrame:
    """Lee un .bib exportado desde Scopus y retorna un DataFrame."""
    try:
        import bibtexparser
        from bibtexparser.bparser import BibTexParser
        from bibtexparser.customization import convert_to_unicode
    except ImportError:
        raise ImportError("Instala bibtexparser: pip install bibtexparser")

    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode

    with open(path, encoding="utf-8", errors="replace") as f:
        db = bibtexparser.load(f, parser=parser)

    records = []
    for e in db.entries:
        authors_raw = e.get("author", "")
        authors = [a.strip() for a in authors_raw.split(" and ") if a.strip()]

        keywords_raw = e.get("keywords", "") or e.get("author_keywords", "")
        keywords = [k.strip() for k in re.split(r"[;,]", keywords_raw) if k.strip()]

        affiliations_raw = e.get("affiliations", "")
        countries = _extract_countries(affiliations_raw)

        records.append({
            "id": e.get("ID", ""),
            "type": e.get("ENTRYTYPE", ""),
            "title": _clean(e.get("title", "")),
            "year": _to_int(e.get("year")),
            "journal": _clean(e.get("journal", "")),
            "volume": e.get("volume", ""),
            "doi": e.get("doi", ""),
            "abstract": _clean(e.get("abstract", "")),
            "authors": authors,
            "author_count": len(authors),
            "keywords": keywords,
            "affiliations": _clean(affiliations_raw),
            "countries": countries,
            "cited_by": _extract_cited_by(e.get("note", "")),
            "language": e.get("language", ""),
            "publisher": _clean(e.get("publisher", "")),
            "source": "Scopus",
        })

    return pd.DataFrame(records)


def parse_wos_txt(path: str | Path) -> pd.DataFrame:
    """Lee un .txt exportado desde WoS (formato de etiquetas de campo)."""
    records = []
    current: dict = {}
    current_field = None

    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("ER"):
                if current:
                    records.append(_process_wos_record(current))
                    current = {}
                    current_field = None
            elif len(line) >= 2 and line[2:3] == " " and line[:2].strip():
                current_field = line[:2].strip()
                current.setdefault(current_field, [])
                val = line[3:].strip()
                if val:
                    current[current_field].append(val)
            elif line.startswith("   ") and current_field:
                current[current_field].append(line.strip())

    return pd.DataFrame(records)


def _process_wos_record(raw: dict) -> dict:
    authors = raw.get("AU", [])
    keywords = raw.get("DE", []) + raw.get("ID", [])
    countries_raw = " ".join(raw.get("C1", []))
    countries = _extract_countries(countries_raw)
    cited_raw = raw.get("TC", ["0"])
    year_raw = raw.get("PY", [""])

    return {
        "id": " ".join(raw.get("UT", [""])),
        "type": "article",
        "title": " ".join(raw.get("TI", [""])),
        "year": _to_int(year_raw[0] if year_raw else None),
        "journal": " ".join(raw.get("SO", [""])),
        "volume": " ".join(raw.get("VL", [""])),
        "doi": " ".join(raw.get("DI", [""])),
        "abstract": " ".join(raw.get("AB", [""])),
        "authors": authors,
        "author_count": len(authors),
        "keywords": keywords,
        "affiliations": " | ".join(raw.get("C1", [])),
        "countries": countries,
        "cited_by": _to_int(cited_raw[0] if cited_raw else 0),
        "language": " ".join(raw.get("LA", [""])),
        "publisher": " ".join(raw.get("PU", [""])),
        "source": "WoS",
    }


def parse_excel(path: str | Path) -> pd.DataFrame:
    """Lee un .xlsx/.xls y lo convierte al formato estándar."""
    df = pd.read_excel(path)

    # Normalizar nombres de columnas (case-insensitive matching)
    col_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        # Mapeo de variaciones comunes
        if col_lower in ("title", "título"):
            col_map[col] = "title"
        elif col_lower in ("author", "authors", "autores", "author_list"):
            col_map[col] = "authors"
        elif col_lower in ("year", "año", "publication_year"):
            col_map[col] = "year"
        elif col_lower in ("journal", "revista", "source", "publication"):
            col_map[col] = "journal"
        elif col_lower in ("volume", "volumen"):
            col_map[col] = "volume"
        elif col_lower in ("doi", "digital_object_identifier"):
            col_map[col] = "doi"
        elif col_lower in ("abstract", "resumen", "abstract_text"):
            col_map[col] = "abstract"
        elif col_lower in ("keyword", "keywords", "palabras clave", "keywords_plus"):
            col_map[col] = "keywords"
        elif col_lower in ("affiliation", "affiliations", "afiliación"):
            col_map[col] = "affiliations"
        elif col_lower in ("language", "idioma"):
            col_map[col] = "language"
        elif col_lower in ("publisher", "editorial", "publicador"):
            col_map[col] = "publisher"
        elif col_lower in ("type", "document_type", "tipo"):
            col_map[col] = "type"
        elif col_lower in ("cited_by", "cited by", "citado por", "citations"):
            col_map[col] = "cited_by"

    df = df.rename(columns=col_map)

    # Asegurar columnas mínimas
    for col in ["title", "authors", "year", "journal", "doi", "abstract", "keywords", "affiliations", "language", "publisher", "type", "volume"]:
        if col not in df.columns:
            df[col] = ""

    # Normalizar datos
    df["title"] = df["title"].fillna("").apply(_clean)
    df["journal"] = df["journal"].fillna("").apply(_clean)
    df["abstract"] = df["abstract"].fillna("").apply(_clean)
    df["affiliations"] = df["affiliations"].fillna("").apply(_clean)
    df["doi"] = df["doi"].fillna("").astype(str)
    df["language"] = df["language"].fillna("")
    df["publisher"] = df["publisher"].fillna("").apply(_clean)
    df["type"] = df["type"].fillna("Journal")
    df["volume"] = df["volume"].fillna("")

    # Convertir año a int
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    # Procesar autores: si es string, convertir a lista
    def parse_authors(val):
        if isinstance(val, list):
            return val
        if pd.isna(val) or val == "":
            return []
        s = str(val).strip()
        # Soporta: "A, B; C, D" o "A and B and C"
        if " and " in s.lower():
            return [a.strip() for a in re.split(r"\s+and\s+", s, flags=re.IGNORECASE) if a.strip()]
        else:
            return [a.strip() for a in re.split(r"[;,]", s) if a.strip()]

    df["authors"] = df["authors"].apply(parse_authors)
    df["author_count"] = df["authors"].apply(len)

    # Procesar keywords: si es string, convertir a lista
    def parse_keywords(val):
        if isinstance(val, list):
            return val
        if pd.isna(val) or val == "":
            return []
        s = str(val).strip()
        return [k.strip() for k in re.split(r"[;,]", s) if k.strip()]

    df["keywords"] = df["keywords"].apply(parse_keywords)

    # Normalizar afiliaciones
    df["affiliations"] = df["affiliations"].apply(_normalize_affiliations)

    # Extraer países de afiliaciones
    df["countries"] = df["affiliations"].apply(_extract_countries)

    # Procesar cited_by
    if "cited_by" in df.columns:
        df["cited_by"] = pd.to_numeric(df["cited_by"], errors="coerce").fillna(0).astype(int)
    else:
        df["cited_by"] = 0

    # Agregar ID e source
    if "id" not in df.columns:
        df["id"] = df.index.astype(str)
    df["source"] = "Excel"

    # Mantener solo columnas estándar
    cols = ["id", "type", "title", "year", "journal", "volume", "doi", "abstract",
            "authors", "author_count", "keywords", "affiliations", "countries",
            "cited_by", "language", "publisher", "source"]
    df = df[[c for c in cols if c in df.columns]]

    return df


def load_data(*paths: str | Path) -> pd.DataFrame:
    """Carga uno o más archivos .bib, .txt o .xlsx y los combina."""
    frames = []
    for p in paths:
        p = Path(p)
        if p.suffix.lower() == ".bib":
            frames.append(parse_scopus_bib(p))
        elif p.suffix.lower() in (".txt", ".tsv"):
            frames.append(parse_wos_txt(p))
        elif p.suffix.lower() in (".xlsx", ".xls"):
            frames.append(parse_excel(p))
        else:
            raise ValueError(f"Formato no soportado: {p.suffix}")

    df = pd.concat(frames, ignore_index=True)
    # Deduplicar por DOI cuando viene de ambas fuentes
    df = df.drop_duplicates(subset=["doi"], keep="first").reset_index(drop=True)
    return df


# ── helpers ──────────────────────────────────────────────────────────────────

_COUNTRY_PATTERNS = [
    "Argentina", "Australia", "Austria", "Belgium", "Bolivia", "Brazil", "Canada",
    "Chile", "China", "Colombia", "Croatia", "Czech", "Denmark", "Ecuador",
    "Egypt", "Finland", "France", "Germany", "Greece", "Hungary", "India",
    "Indonesia", "Iran", "Iraq", "Israel", "Italy", "Japan", "Jordan",
    "Malaysia", "Mexico", "Netherlands", "New Zealand", "Nigeria", "Norway",
    "Pakistan", "Peru", "Philippines", "Poland", "Portugal", "Qatar",
    "Romania", "Russia", "Saudi Arabia", "Singapore", "Slovenia", "South Africa",
    "South Korea", "Korea", "Spain", "Sweden", "Switzerland", "Taiwan",
    "Thailand", "Turkey", "Ukraine", "United Arab Emirates", "UAE",
    "United Kingdom", "UK", "United States", "USA", "Uruguay", "Venezuela",
    "Vietnam",
]

_COUNTRY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _COUNTRY_PATTERNS) + r")\b",
    re.IGNORECASE,
)

_NORMALIZE = {
    "usa": "United States", "uk": "United Kingdom",
    "uae": "United Arab Emirates", "korea": "South Korea",
}


def _normalize_affiliations(aff_text: str) -> str:
    """Homologa variaciones de nombre de instituciones."""
    if not aff_text or not isinstance(aff_text, str):
        return ""

    # Separar múltiples instituciones (separadas por |)
    affiliations = [a.strip() for a in aff_text.split("|")]

    normalized = []
    seen = set()

    for aff in affiliations:
        if not aff:
            continue

        # Estrategia: Buscar la institución principal
        # Patterns: "Instituto de X, Universidad Y, País"
        # Preferimos extraer "Universidad Y"
        inst_name = _extract_main_institution(aff)

        if inst_name and inst_name not in seen:
            normalized.append(inst_name)
            seen.add(inst_name)

    return " | ".join(normalized) if normalized else aff_text.split("|")[0].strip()


def _extract_main_institution(aff_text: str) -> str:
    """Extrae el nombre principal de una afiliación."""
    if not aff_text:
        return ""

    parts = [p.strip() for p in aff_text.split(",")]

    # Palabras clave que indican institución principal
    keywords = [
        "university", "universidad", "universität", "università",
        "institute", "instituto", "center", "centre", "laboratory",
        "college", "école", "school", "escuela", "politecnico",
    ]

    # Buscar partes con palabras clave de institución
    candidates = []
    for i, part in enumerate(parts):
        part_lower = part.lower()
        if any(kw in part_lower for kw in keywords):
            candidates.append((i, part))

    if candidates:
        # Preferir la última institución importante (generalmente la más específica)
        idx, main = candidates[-1]
        return main

    # Si no hay keyword, devolver la primera parte
    return parts[0] if parts else aff_text


def _extract_countries(text: str) -> list[str]:
    found = _COUNTRY_RE.findall(text)
    normalized = [_NORMALIZE.get(c.lower(), c.title()) for c in found]
    return list(dict.fromkeys(normalized))  # unique, preserving order


def _extract_cited_by(note: str) -> int:
    m = re.search(r"Cited by:\s*(\d+)", note or "")
    return int(m.group(1)) if m else 0


def _to_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
