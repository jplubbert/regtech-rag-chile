"""CLI interactiva: pregunta del usuario → respuesta JSON estructurada."""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.respuesta import generar_respuesta


def main() -> None:
    print("Asistente sobre Ley 20.009 (ENTER vacío para salir).\n")
    while True:
        try:
            query = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not query:
            break
        try:
            result = generar_respuesta(query, k=10)
        except Exception as exc:
            print(f"Error: {exc}\n")
            continue
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
