"""Batch de generar_respuesta sobre las 8 queries del benchmark."""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.respuesta import generar_respuesta

QUERIES = [
    {"n": 1, "query": "¿Cuándo el banco no es responsable de un fraude?"},
    {"n": 2, "query": "¿Qué hago si me roban la tarjeta?"},
    {"n": 3, "query": "¿Qué es autenticación reforzada?"},
    {"n": 4, "query": "Plazo para presentar denuncia ante carabineros"},
    {"n": 5, "query": "Si el cliente entregó voluntariamente sus claves a un tercero, ¿el banco debe devolverle el dinero?"},
    {"n": 6, "query": "¿Cuántos factores requiere la autenticación reforzada?"},
    {"n": 7, "query": "transferencias entre cuentas propias del titular"},
    {"n": 8, "query": "¿En qué casos puede el banco solicitar suspensión judicial de la restitución?"},
]


def main() -> None:
    for q in QUERIES:
        print("=" * 80)
        print(f"Q{q['n']}: {q['query']}")
        print("=" * 80)
        try:
            result = generar_respuesta(q["query"], k=10)
        except Exception as exc:
            print(f"ERROR: {exc}\n")
            continue
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
