"""
paper_analyzer.py — Análisis de papers completos con Claude API

Flujo:
  DOI → Semantic Scholar (PDF OA / arXiv) → pdfplumber → Claude → ficha estructurada

Si no hay PDF disponible, analiza solo el abstract de Scopus/WoS.
"""

from __future__ import annotations
import os
import re
import json
import time
import hashlib
from pathlib import Path

import requests
import pdfplumber
import anthropic

# ── config ────────────────────────────────────────────────────────────────────

def _load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            k, _, v = line.strip().partition("=")
            if k and k not in os.environ:
                os.environ[k] = v

_load_env()

PDF_CACHE_DIR = Path(__file__).parent / ".pdf_cache"
PDF_CACHE_DIR.mkdir(exist_ok=True)

ANALYSIS_CACHE = Path(__file__).parent / ".analysis_cache.json"

HEADERS = {
    "User-Agent": "SciMap/1.0 (academic research tool; contact: research@scimap.app)"
}

# ── caché de análisis ─────────────────────────────────────────────────────────

def _load_analysis_cache() -> dict:
    if ANALYSIS_CACHE.exists():
        try:
            return json.loads(ANALYSIS_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_analysis_cache(cache: dict):
    ANALYSIS_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── obtener PDF ───────────────────────────────────────────────────────────────

def _doi_to_cache_key(doi: str) -> str:
    return hashlib.md5(doi.encode()).hexdigest()


def get_pdf_path(doi: str) -> Path | None:
    """
    Intenta obtener el PDF de un paper por DOI.
    Orden: caché local → Semantic Scholar (OA) → arXiv.
    Retorna path al PDF o None si no está disponible.
    """
    cache_key = _doi_to_cache_key(doi)
    cached = PDF_CACHE_DIR / f"{cache_key}.pdf"
    if cached.exists() and cached.stat().st_size > 5000:
        return cached

    # Semantic Scholar
    try:
        r = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "openAccessPdf,externalIds"},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            data    = r.json()
            oa      = data.get("openAccessPdf") or {}
            pdf_url = oa.get("url")
            arxiv   = (data.get("externalIds") or {}).get("ArXiv")

            # Intentar PDF OA
            if pdf_url:
                pdf = _download_pdf(pdf_url, cached)
                if pdf:
                    return pdf

            # Intentar arXiv
            if arxiv:
                pdf = _download_pdf(f"https://arxiv.org/pdf/{arxiv}", cached)
                if pdf:
                    return pdf
    except Exception:
        pass

    return None


def _download_pdf(url: str, dest: Path) -> Path | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if r.status_code == 200 and b"%PDF" in r.content[:10]:
            dest.write_bytes(r.content)
            return dest
    except Exception:
        pass
    return None


# ── extraer texto ─────────────────────────────────────────────────────────────

def extract_text(pdf_path: Path, max_pages: int = 12) -> str:
    """Extrae texto de las primeras N páginas del PDF."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:max_pages]:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception:
        pass
    # Limpiar espacios dobles y saltos excesivos
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ── análisis con Claude ───────────────────────────────────────────────────────

_SCHEMA_FULL = '''{
  "titulo": "titulo completo",
  "anio": 2025,
  "autores": ["lista de autores"],
  "journal_venue": "nombre del journal o conferencia",
  "pregunta_investigacion": "pregunta principal que responde el paper",
  "objetivo": "objetivo general en 1-2 oraciones",
  "metodologia": {
    "tipo": "experimental | revision sistematica | teorico | caso de estudio | encuesta | mixto",
    "descripcion": "descripcion breve del metodo",
    "datos": "que datos usa o produce",
    "herramientas": ["software, modelos, datasets usados"]
  },
  "contribuciones": ["lista de 3-5 contribuciones principales"],
  "resultados_clave": ["resultados mas importantes con numeros si los hay"],
  "limitaciones": ["limitaciones reconocidas"],
  "trabajo_futuro": ["lineas futuras mencionadas"],
  "conceptos_clave": ["5-10 conceptos centrales del paper"],
  "area_conocimiento": "area principal (ej: Machine Learning, Astronomia, Biomedicina)",
  "relevancia_score": 8,
  "resumen_ejecutivo": "resumen en espanol de 3-4 oraciones para un investigador no especialista"
}'''

_SCHEMA_ABSTRACT = '''{
  "titulo": "titulo completo",
  "anio": null,
  "autores": [],
  "journal_venue": "",
  "pregunta_investigacion": "inferida del abstract",
  "objetivo": "inferido del abstract",
  "metodologia": {
    "tipo": "experimental | revision | teorico | otro",
    "descripcion": "inferida",
    "datos": "",
    "herramientas": []
  },
  "contribuciones": ["inferidas del abstract"],
  "resultados_clave": ["mencionados en el abstract"],
  "limitaciones": [],
  "trabajo_futuro": [],
  "conceptos_clave": ["5-8 conceptos del abstract"],
  "area_conocimiento": "area principal",
  "relevancia_score": 5,
  "resumen_ejecutivo": "resumen en espanol de 2-3 oraciones",
  "fuente": "solo abstract"
}'''

def _build_prompt_full(text: str) -> str:
    return (
        "Analiza este paper cientifico y entrega una ficha estructurada en JSON.\n"
        "Responde SOLO con JSON valido, sin texto adicional.\n\n"
        + _SCHEMA_FULL
        + "\n\nTEXTO DEL PAPER (primeras paginas):\n"
        + text[:12000]
    )

def _build_prompt_abstract(text: str) -> str:
    return (
        "Analiza este abstract de paper cientifico y entrega una ficha en JSON.\n"
        "Responde SOLO con JSON valido, sin texto adicional.\n"
        "Nota: el analisis es parcial porque solo tienes el abstract.\n\n"
        + _SCHEMA_ABSTRACT
        + "\n\nABSTRACT:\n"
        + text[:3000]
    )


def analyze_paper(
    doi: str,
    title: str = "",
    abstract: str = "",
    force_refresh: bool = False,
) -> dict:
    """
    Analiza un paper por DOI usando Claude.
    Intenta obtener el PDF completo; si falla, usa el abstract.
    Usa caché para no repetir análisis.
    """
    cache = _load_analysis_cache()
    cache_key = _doi_to_cache_key(doi)

    if not force_refresh and cache_key in cache:
        return cache[cache_key]

    client = anthropic.Anthropic()
    result = {"doi": doi, "titulo": title, "error": None, "fuente_texto": None}

    # Intentar PDF completo
    pdf_path = get_pdf_path(doi)
    if pdf_path:
        text = extract_text(pdf_path)
        if len(text) > 500:
            prompt   = _build_prompt_full(text)
            result["fuente_texto"] = "PDF completo"
        else:
            pdf_path = None

    # Fallback a abstract
    if not pdf_path:
        if not abstract:
            result["error"] = "Sin PDF ni abstract disponible"
            return result
        prompt = _build_prompt_abstract(abstract)
        result["fuente_texto"] = "Solo abstract"

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()

        # Extraer JSON si viene envuelto en markdown
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
            if m:
                raw = m.group(1).strip()

        # Buscar el primer bloque JSON { ... }
        m = re.search(r"\{[\s\S]+\}", raw)
        if m:
            raw = m.group(0)

        parsed = json.loads(raw)
        result.update(parsed)
        result["doi"] = doi

        cache[cache_key] = result
        _save_analysis_cache(cache)

    except json.JSONDecodeError as e:
        result["error"] = f"Error parsing JSON: {e}"
        result["raw_response"] = raw[:500]
    except Exception as e:
        result["error"] = str(e)

    return result


# ── análisis en lote ──────────────────────────────────────────────────────────

def analyze_batch(
    df,
    max_papers: int = 20,
    use_pdf: bool = True,
    delay: float = 1.0,
) -> list[dict]:
    """
    Analiza múltiples papers del DataFrame.
    df debe tener columnas: doi, title, abstract
    """
    cache   = _load_analysis_cache()
    results = []

    papers = df.dropna(subset=["doi"]).head(max_papers)

    for i, (_, row) in enumerate(papers.iterrows()):
        doi      = str(row.get("doi", ""))
        title    = str(row.get("title", ""))
        abstract = str(row.get("abstract", ""))

        cache_key = _doi_to_cache_key(doi)
        if cache_key in cache:
            results.append(cache[cache_key])
            print(f"[{i+1}/{len(papers)}] Cache: {title[:50]}")
            continue

        print(f"[{i+1}/{len(papers)}] Analizando: {title[:50]}...")
        result = analyze_paper(doi, title, abstract)
        results.append(result)

        if result.get("error"):
            print(f"  Error: {result['error']}")
        else:
            print(f"  OK ({result.get('fuente_texto','?')}) - {result.get('area_conocimiento','')}")

        time.sleep(delay)

    return results


# ── formatear para dashboard ──────────────────────────────────────────────────

def format_paper_card(analysis: dict) -> str:
    """Genera HTML de ficha de paper para el dashboard."""
    if analysis.get("error"):
        return f'<p style="color:#EF4444">Error: {analysis["error"]}</p>'

    contribs = "".join(f"<li>{c}</li>" for c in analysis.get("contribuciones", []))
    results  = "".join(f"<li>{r}</li>" for r in analysis.get("resultados_clave", []))
    lims     = "".join(f"<li>{l}</li>" for l in analysis.get("limitaciones", []))
    kws      = " ".join(
        f'<span style="background:#EFF6FF;color:#2563EB;padding:2px 8px;'
        f'border-radius:99px;font-size:0.75rem;margin:2px">{k}</span>'
        for k in analysis.get("conceptos_clave", [])
    )

    fuente_badge = (
        '<span style="background:#D1FAE5;color:#065F46;padding:2px 8px;border-radius:99px;font-size:0.72rem">PDF completo</span>'
        if analysis.get("fuente_texto") == "PDF completo"
        else '<span style="background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:99px;font-size:0.72rem">Solo abstract</span>'
    )

    return f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:800px">
      <div style="background:#1E3A5F;color:white;padding:1.2rem;border-radius:10px 10px 0 0">
        <div style="font-size:0.75rem;opacity:.7;margin-bottom:4px">{analysis.get('area_conocimiento','')} · {fuente_badge}</div>
        <div style="font-size:1.1rem;font-weight:700">{analysis.get('titulo','')}</div>
        <div style="font-size:0.82rem;opacity:.8;margin-top:4px">{analysis.get('journal_venue','')} · {analysis.get('anio','')}</div>
      </div>
      <div style="border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:1.2rem">
        <p style="background:#F0FDF4;border-left:4px solid #10B981;padding:.8rem;border-radius:4px;font-size:.9rem;margin:0 0 1rem">
          {analysis.get('resumen_ejecutivo','')}
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
          <div>
            <b style="color:#2563EB">🔍 Pregunta de investigación</b>
            <p style="font-size:.85rem;margin:.3rem 0">{analysis.get('pregunta_investigacion','')}</p>
            <b style="color:#2563EB">🧪 Metodología</b>
            <p style="font-size:.85rem;margin:.3rem 0">
              <span style="background:#EFF6FF;padding:2px 6px;border-radius:4px">{analysis.get('metodologia',{}).get('tipo','')}</span>
              — {analysis.get('metodologia',{}).get('descripcion','')}
            </p>
            <b style="color:#2563EB">💡 Contribuciones</b>
            <ul style="font-size:.83rem;margin:.3rem 0;padding-left:1.2rem">{contribs}</ul>
          </div>
          <div>
            <b style="color:#10B981">📊 Resultados clave</b>
            <ul style="font-size:.83rem;margin:.3rem 0;padding-left:1.2rem">{results}</ul>
            <b style="color:#F59E0B">⚠️ Limitaciones</b>
            <ul style="font-size:.83rem;margin:.3rem 0;padding-left:1.2rem">{lims}</ul>
          </div>
        </div>
        <div style="margin-top:.8rem">{kws}</div>
      </div>
    </div>
    """
