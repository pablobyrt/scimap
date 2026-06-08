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


def load_data(*paths: str | Path) -> pd.DataFrame:
    """Carga uno o más archivos .bib o .txt y los combina."""
    frames = []
    for p in paths:
        p = Path(p)
        if p.suffix.lower() == ".bib":
            frames.append(parse_scopus_bib(p))
        elif p.suffix.lower() in (".txt", ".tsv"):
            frames.append(parse_wos_txt(p))
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
