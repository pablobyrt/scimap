"""
gender_engine.py — Motor de inferencia de género para Scimap

Algoritmo en 3 pasos (por orden de confianza):
  1. gender-guesser  — base de datos offline, instantáneo
  2. genderize.io    — API gratuita (100 req/día), cubre nombres no occidentales
  3. Web search      — búsqueda por nombre completo + institución como último recurso

Cada nombre se clasifica en:
  Masculino | Femenino | Ambiguo | Desconocido

El motor tiene caché en disco para no repetir búsquedas entre sesiones.
"""

from __future__ import annotations
import re
import json
import time
import logging
from pathlib import Path
from collections import Counter

import pandas as pd
import requests

log = logging.getLogger(__name__)

# ── caché en disco ────────────────────────────────────────────────────────────
CACHE_FILE = Path(__file__).parent / ".gender_cache.json"

def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

# ── diccionario manual (nombres sin cobertura en gender-guesser) ─────────────
MANUAL: dict[str, str] = {
    # Indios — Masculino
    "Parag": "M", "Swagat": "M", "Tushar": "M", "Akshat": "M", "Abhishek": "M",
    "Jayanta": "M", "Srustidhar": "M", "Pavan": "M", "Brij": "M", "Mosiur": "M",
    "Utkarsh": "M", "Durga": "M", "Ravi": "M", "Praveen": "M", "Anirudh": "M",
    "Umamaheswara": "M", "Madhava": "M", "Savvas": "M", "Bayron": "M",
    # Indios — Ambiguo
    "Saumya": "A",
    # Árabes / Medio Oriente
    "Youniss": "M", "Dalya": "F", "Tarek": "M", "Obed": "M",
    # Latinoamericanos no reconocidos
    "Angelo": "M", "Cristian": "M", "Jhon": "M", "Clayder": "M",
    "Bastian": "M", "Fabian": "M", "Anibal": "M", "Erico": "M",
    "Maibeth": "F", "Lorayne": "F", "Tabita": "F", "Thais": "F",
    # Nombres compuestos frecuentes
    "Jean-Baptiste": "M", "Jean-Pierre": "M", "Jean-Luc": "M",
    "Marie-Claire": "F", "Marie-Laure": "F",
    # Coreanos
    "Eunji": "F", "Junho": "M", "Jiyeon": "F", "Hyunwoo": "M",
    # Chinos — clasificables
    "Jiehong": "M", "Shengjie": "M", "Danyue": "F", "Songlin": "M",
    "Wenzhao": "M", "Xiaoming": "M", "Yanfei": "F",
    # Chinos — ambiguos
    "Jie": "A", "Zichen": "A", "Bao": "A", "Lei": "A", "Yang": "A",
    # Europeos no reconocidos
    "Tjark": "M", "Mikko": "M", "Coryn": "M", "Hubert": "M",
    "Pietro": "M", "Lorenzo": "M", "Romain": "M", "Rodolphe": "M",
    "Karina": "F", "Laura": "F", "Valeria": "F", "Elena": "F",
    "Ruby": "F", "Ines": "F",
    # Sri Lanka / otro
    "Saliya": "M",
}

# Normalización de acentos para búsqueda en MANUAL
_ACCENT = str.maketrans(
    "áéíóúÁÉÍÓÚàèìòùÀÈÌÒÙäëïöüÄËÏÖÜñÑ",
    "aeiouAEIOUaeiouAEIOUaeiouAEIOUnN"
)

GENDER_MAP = {"M": "Masculino", "F": "Femenino", "A": "Ambiguo"}

LABEL_MAP = {
    "male":         "Masculino",
    "mostly_male":  "Masculino",   # colapsa para simplicidad
    "female":       "Femenino",
    "mostly_female":"Femenino",
    "andy":         "Ambiguo",
    "unknown":      "Desconocido",
}


# ── extracción del primer nombre ──────────────────────────────────────────────

def extract_first_name(author: str) -> str:
    """
    Extrae el primer nombre real de una cadena de autor.
    Soporta formatos:
      - "Apellido, Nombre Completo"
      - "Apellido, N. Nombre"     → toma el primer no-inicial
      - "Nombre Apellido"
    """
    author = author.strip()
    if "," in author:
        given = author.split(",", 1)[1].strip()
    else:
        parts = author.split()
        given = " ".join(parts[:-1]) if len(parts) > 1 else author

    # Toma el primer token que no sea una inicial (X.)
    for token in given.split():
        clean = token.rstrip(".")
        if len(clean) > 1 and not token.endswith("."):
            return clean
    return ""


# ── paso 1: gender-guesser (offline) ─────────────────────────────────────────

def _step_guesser(name: str) -> str | None:
    """Retorna género si es claro, None si es desconocido/ambiguo."""
    try:
        import gender_guesser.detector as gg
        d = gg.Detector(case_sensitive=False)
        raw = d.get_gender(name)
        return LABEL_MAP.get(raw)
    except ImportError:
        return None


# ── paso 2: genderize.io API ──────────────────────────────────────────────────

def _step_genderize(names: list[str], cache: dict) -> dict[str, str]:
    """
    Consulta la API gratuita de genderize.io para una lista de nombres.
    Retorna {nombre: género}.
    Documentación: https://genderize.io
    """
    to_query = [n for n in names if n and f"gz:{n.lower()}" not in cache]
    if not to_query:
        return {}

    results = {}
    # Genderize acepta hasta 10 nombres por request
    batch_size = 10
    for i in range(0, len(to_query), batch_size):
        batch = to_query[i : i + batch_size]
        params = [("name[]", n) for n in batch]
        try:
            resp = requests.get(
                "https://api.genderize.io",
                params=params,
                timeout=10,
            )
            if resp.status_code == 200:
                for item in resp.json():
                    raw_name  = item.get("name", "").lower()
                    gender    = item.get("gender")        # "male" | "female" | null
                    prob      = item.get("probability", 0)
                    count     = item.get("count", 0)

                    # Solo confiar si hay suficientes muestras y probabilidad alta
                    if gender and prob >= 0.80 and count >= 10:
                        label = "Masculino" if gender == "male" else "Femenino"
                    elif gender and prob >= 0.60 and count >= 5:
                        label = "Masculino" if gender == "male" else "Femenino"
                    else:
                        label = "Desconocido"

                    results[raw_name] = label
                    cache[f"gz:{raw_name}"] = label
            time.sleep(0.3)   # respetar rate limit
        except Exception as e:
            log.warning(f"genderize.io error: {e}")

    return results


# ── paso 3: web search por nombre completo ────────────────────────────────────

def _step_web_search(full_name: str, institution: str, cache: dict) -> str:
    """
    Busca el perfil del autor en la web usando DuckDuckGo Lite.
    Detecta género por pronombres en el snippet ("his", "her", "she", "he").
    """
    cache_key = f"web:{full_name.lower()}"
    if cache_key in cache:
        return cache[cache_key]

    query = f"{full_name} researcher {institution}".strip()
    url = "https://lite.duckduckgo.com/lite/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SciMap/1.0)"}

    try:
        resp = requests.get(
            url, params={"q": query}, headers=headers, timeout=8
        )
        text = resp.text.lower()

        # Contar indicadores de género en el texto de resultados
        male_score   = text.count(" he ") + text.count(" his ") + text.count(" him ")
        female_score = text.count(" she ") + text.count(" her ")

        if female_score > male_score and female_score >= 2:
            result = "Femenino"
        elif male_score > female_score and male_score >= 2:
            result = "Masculino"
        else:
            result = "Desconocido"

        cache[cache_key] = result
        return result
    except Exception as e:
        log.warning(f"Web search error for {full_name}: {e}")
        return "Desconocido"


# ── motor principal ───────────────────────────────────────────────────────────

def infer_gender(
    name: str,
    full_author_str: str = "",
    institution: str = "",
    cache: dict | None = None,
    use_genderize: bool = True,
    use_web: bool = False,
) -> dict:
    """
    Infiere el género de un autor usando el algoritmo de 3 pasos.

    Retorna:
        {
            "first_name": str,
            "gender": str,       # Masculino | Femenino | Ambiguo | Desconocido
            "method": str,       # offline | manual | genderize | web | unknown
            "confidence": str,   # Alta | Media | Baja
        }
    """
    if cache is None:
        cache = {}

    first = extract_first_name(name)
    if not first:
        return {"first_name": "", "gender": "Desconocido", "method": "unknown", "confidence": "—"}

    norm = first.translate(_ACCENT)

    # ── Paso 0: diccionario manual (mayor prioridad) ──────────────────────────
    for key in [first, norm]:
        if key in MANUAL:
            return {
                "first_name": first,
                "gender": GENDER_MAP[MANUAL[key]],
                "method": "manual",
                "confidence": "Alta",
            }

    # ── Paso 1: gender-guesser ────────────────────────────────────────────────
    gz_key = f"gz:{first.lower()}"
    if gz_key in cache:
        gender = cache[gz_key]
        if gender != "Desconocido":
            return {"first_name": first, "gender": gender, "method": "offline (caché)", "confidence": "Alta"}
    else:
        gender = _step_guesser(first)
        if gender and gender != "Desconocido":
            cache[gz_key] = gender
            return {"first_name": first, "gender": gender, "method": "offline", "confidence": "Alta"}

    # ── Paso 2: genderize.io ──────────────────────────────────────────────────
    if use_genderize:
        gz_results = _step_genderize([first], cache)
        gender = gz_results.get(first.lower(), cache.get(gz_key, "Desconocido"))
        if gender != "Desconocido":
            return {"first_name": first, "gender": gender, "method": "genderize.io", "confidence": "Media"}

    # ── Paso 3: web search ────────────────────────────────────────────────────
    if use_web and full_author_str:
        gender = _step_web_search(full_author_str, institution, cache)
        if gender != "Desconocido":
            return {"first_name": first, "gender": gender, "method": "web search", "confidence": "Baja"}

    return {"first_name": first, "gender": "Desconocido", "method": "unknown", "confidence": "—"}


# ── análisis completo del DataFrame ──────────────────────────────────────────

def gender_analysis_df(
    df: pd.DataFrame,
    use_genderize: bool = True,
    use_web: bool = False,
    batch_genderize: bool = True,
) -> pd.DataFrame:
    """
    Aplica inferencia de género a todos los primeros autores del DataFrame.

    Columnas de df requeridas: "authors" (lista de strings)
    Columnas opcionales: "affiliations" (para web search)

    Retorna el mismo DataFrame con columnas adicionales:
        primer_autor, primer_nombre, genero, metodo_inferencia, confianza
    """
    cache = _load_cache()

    # Extraer primeros nombres únicos para batch genderize
    if use_genderize and batch_genderize:
        first_names = []
        for authors in df["authors"]:
            if authors:
                fn = extract_first_name(authors[0])
                norm = fn.translate(_ACCENT)
                if fn and fn not in MANUAL and norm not in MANUAL:
                    first_names.append(fn)

        unique_names = list(set(first_names))
        log.info(f"Consultando genderize.io para {len(unique_names)} nombres únicos...")
        _step_genderize(unique_names, cache)
        _save_cache(cache)

    rows = []
    for _, row in df.iterrows():
        authors = row.get("authors", [])
        first_author = authors[0] if authors else ""
        institution  = row.get("affiliations", "") or ""
        if isinstance(institution, str):
            institution = institution.split(";")[0].split(",")[-1].strip()

        result = infer_gender(
            name            = first_author,
            full_author_str = first_author,
            institution     = institution,
            cache           = cache,
            use_genderize   = use_genderize,
            use_web         = use_web,
        )
        rows.append({
            "primer_autor":       first_author,
            "primer_nombre":      result["first_name"],
            "genero":             result["gender"],
            "metodo_inferencia":  result["method"],
            "confianza":          result["confidence"],
        })

    _save_cache(cache)

    gender_df = pd.DataFrame(rows)
    return pd.concat([df.reset_index(drop=True), gender_df], axis=1)


# ── métricas resumen ──────────────────────────────────────────────────────────

def gender_summary(df_with_gender: pd.DataFrame) -> dict:
    """
    Retorna métricas de género para el dashboard.
    Requiere columna 'genero' en el DataFrame.
    """
    vc = df_with_gender["genero"].value_counts()
    total = len(df_with_gender)
    method_vc = df_with_gender["metodo_inferencia"].value_counts()

    # Por año (si existe columna 'year')
    by_year = pd.DataFrame()
    if "year" in df_with_gender.columns:
        by_year = (
            df_with_gender.dropna(subset=["year"])
            .groupby(["year", "genero"])
            .size()
            .reset_index(name="count")
            .sort_values("year")
        )

    # % de cobertura (no Desconocido)
    coverage = round(100 * (1 - vc.get("Desconocido", 0) / total), 1)

    return {
        "overall":    vc.reset_index().rename(columns={"index": "genero", "genero": "count", "count": "count"}),
        "by_year":    by_year,
        "coverage":   coverage,
        "methods":    method_vc,
        "author_detail": df_with_gender[
            ["primer_autor", "primer_nombre", "genero", "metodo_inferencia", "confianza"]
        ].drop_duplicates(subset=["primer_autor"]).sort_values("genero"),
    }
