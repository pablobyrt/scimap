"""
Uso:
    python main.py archivo1.bib [archivo2.txt ...]

Genera dashboard.html en la misma carpeta.
"""
import sys
from pathlib import Path
import parser as bp
import dashboard as db


def main():
    if len(sys.argv) < 2:
        print("Uso: python main.py <archivo.bib> [archivo2.bib ...]")
        sys.exit(1)

    paths = [Path(p) for p in sys.argv[1:]]
    for p in paths:
        if not p.exists():
            print(f"Archivo no encontrado: {p}")
            sys.exit(1)

    print(f"Cargando {len(paths)} archivo(s)...")
    df = bp.load_data(*paths)
    print(f"  -> {len(df)} documentos cargados")

    out = Path(__file__).parent / "dashboard.html"
    db.build_dashboard(df, out)

    import webbrowser
    webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
