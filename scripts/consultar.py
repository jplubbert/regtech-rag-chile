"""CLI interactiva: pregunta → retrieval → top-k chunks."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.retrieval import buscar_similares


def main() -> None:
    print("Consulta interactiva (ENTER vacío para salir).\n")
    while True:
        try:
            query = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not query:
            break
        try:
            resultados = buscar_similares(query, k=5)
        except Exception as exc:
            print(f"Error: {exc}\n")
            continue
        if not resultados:
            print("(sin resultados — ¿hay documentos indexados?)\n")
            continue
        for i, r in enumerate(resultados, 1):
            preview = r["contenido"][:300]
            if len(r["contenido"]) > 300:
                preview += "..."
            print(
                f"\n[{i}] sim={r['similitud']:.3f}  "
                f"doc={r['documento_nombre']}  "
                f"meta={r['metadata']}"
            )
            print(preview)
        print()


if __name__ == "__main__":
    main()
