"""Benchmark de retrieval en cascada con threshold de confianza.

Compara 3 estrategias sobre las mismas 8 queries:
  (sin)     query original sin expansión
  (glo)     query siempre expandida vía glosario
  (casc)    cascade: expansión solo si sim_top1 < umbral
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.query_expansion import expandir_query
from core.retrieval import buscar_en_cascada, buscar_similares

UMBRAL = 0.6
K = 3

QUERIES = [
    {
        "n": 1,
        "query": "¿Cuándo el banco no es responsable de un fraude?",
        "tag": "abstracta sobre eximición",
        "esperado": [
            {"articulo": 5, "sufijo": "ter"},
            {"articulo": 5, "sufijo": "bis"},
        ],
    },
    {
        "n": 2,
        "query": "¿Qué hago si me roban la tarjeta?",
        "tag": "perspectiva usuario, coloquial",
        "esperado": [{"articulo": 2}],
    },
    {
        "n": 3,
        "query": "¿Qué es autenticación reforzada?",
        "tag": "definición pura",
        "esperado": [{"articulo": 4, "inciso": 10}],
    },
    {
        "n": 4,
        "query": "Plazo para presentar denuncia ante carabineros",
        "tag": "query corta, palabras clave",
        "esperado": [{"articulo": 4, "inciso": 4}],
    },
    {
        "n": 5,
        "query": "Si el cliente entregó voluntariamente sus claves a un tercero, ¿el banco debe devolverle el dinero?",
        "tag": "caso específico con condición",
        "esperado": [{"articulo": 5, "sufijo": "ter", "inciso": 5}],
    },
    {
        "n": 6,
        "query": "¿Cuántos factores requiere la autenticación reforzada?",
        "tag": "numérica específica",
        "esperado": [{"articulo": 4, "inciso": 10}],
    },
    {
        "n": 7,
        "query": "transferencias entre cuentas propias del titular",
        "tag": "frase nominal sin verbo",
        "esperado": [{"articulo": 5, "sufijo": "ter", "inciso": 2}],
    },
    {
        "n": 8,
        "query": "¿En qué casos puede el banco solicitar suspensión judicial de la restitución?",
        "tag": "procedimiento legal",
        "esperado": [
            {"articulo": 5, "sufijo": "bis", "inciso": 1},
            {"articulo": 5, "sufijo": "bis", "inciso": 2},
        ],
    },
]


def matches(metadata: dict, esperado: list[dict]) -> bool:
    art = metadata.get("articulo")
    suf = metadata.get("articulo_sufijo")
    inc = metadata.get("inciso")
    for exp in esperado:
        if exp.get("articulo") is not None and art != exp["articulo"]:
            continue
        if (exp.get("sufijo") or None) != (suf or None):
            continue
        if "inciso" in exp and inc != exp["inciso"]:
            continue
        return True
    return False


def primer_rank(chunks: list[dict], esperado: list[dict]) -> int | None:
    for rank, c in enumerate(chunks, 1):
        if matches(c["metadata"], esperado):
            return rank
    return None


def _rank_str(r: int | None) -> str:
    return "miss" if r is None else str(r)


def main() -> None:
    # Preview: ver las 8 expansiones (independiente de si la cascada las usa).
    print("=" * 110)
    print("EXPANSIONES (vista previa, una por query)")
    print("=" * 110)
    for q in QUERIES:
        exp = expandir_query(q["query"], modo="glosario")
        print(f"\nQ{q['n']}  [{q['tag']}]")
        print(f"  original:  {q['query']}")
        print(f"  expandida: {exp}")

    # Run cascade for each query
    cascada = []
    for q in QUERIES:
        result = buscar_en_cascada(q["query"], k=K, umbral=UMBRAL)
        rank = primer_rank(result["chunks"], q["esperado"])
        cascada.append({
            "n": q["n"],
            "tag": q["tag"],
            "estrategia": result["estrategia"],
            "sim_top1": result["sim_top1"],
            "rank": rank,
            "query_usada": result["query_usada"],
        })

    # Run baselines
    sin = []
    for q in QUERIES:
        chunks = buscar_similares(q["query"], k=K, expandir=False)
        sin.append({
            "n": q["n"],
            "sim_top1": chunks[0]["similitud"] if chunks else 0.0,
            "rank": primer_rank(chunks, q["esperado"]),
        })

    glo = []
    for q in QUERIES:
        exp = expandir_query(q["query"], modo="glosario")
        chunks = buscar_similares(exp, k=K, expandir=False)
        glo.append({
            "n": q["n"],
            "sim_top1": chunks[0]["similitud"] if chunks else 0.0,
            "rank": primer_rank(chunks, q["esperado"]),
        })

    # Trace per query
    print("=" * 110)
    print(f"CASCADA (umbral={UMBRAL}, k={K})")
    print("=" * 110)
    for q, c in zip(QUERIES, cascada):
        gatillado = c["estrategia"] != "original"
        print(f"\nQ{q['n']}  [{q['tag']}]")
        print(f"  query original: {q['query']}")
        if gatillado:
            print(f"  query expandida: {c['query_usada']}")
        print(
            f"  estrategia: {c['estrategia']}  "
            f"sim_top1: {c['sim_top1']:.3f}  "
            f"rank: {_rank_str(c['rank'])}"
        )

    # Comparative table
    print("\n" + "=" * 110)
    print("TABLA COMPARATIVA (sin / glosario forzado / cascada)")
    print("=" * 110)
    print(
        f"{'Q':>2}  {'TIPO':<28}  "
        f"{'sim/sin':>7} {'r/sin':>5}    "
        f"{'sim/glo':>7} {'r/glo':>5}    "
        f"{'sim/casc':>8} {'r/casc':>6}    "
        f"estrategia"
    )
    print("-" * 110)
    for s, g, c in zip(sin, glo, cascada):
        print(
            f"{s['n']:>2}  {c['tag'][:28]:<28}  "
            f"{s['sim_top1']:>7.3f} {_rank_str(s['rank']):>5}    "
            f"{g['sim_top1']:>7.3f} {_rank_str(g['rank']):>5}    "
            f"{c['sim_top1']:>8.3f} {_rank_str(c['rank']):>6}    "
            f"{c['estrategia']}"
        )

    # Summary
    print("\n" + "=" * 110)
    print("RESUMEN")
    print("=" * 110)
    n = len(QUERIES)

    def stats(data, label):
        t1 = sum(1 for x in data if x["rank"] == 1)
        t3 = sum(1 for x in data if x["rank"] is not None)
        avg = sum(x["sim_top1"] for x in data) / n
        return label, t1, t3, avg

    rows = [stats(sin, "sin expansión"),
            stats(glo, "glosario forzado"),
            stats(cascada, "cascada (umbral=0.6)")]

    print(f"{'estrategia':<24}{'top-1':>10}{'top-3':>10}{'sim_avg':>10}")
    for label, t1, t3, avg in rows:
        print(f"{label:<24}{t1:>4}/{n:<5}{t3:>4}/{n:<5}{avg:>10.3f}")

    print()
    cuantas_expandidas = sum(1 for c in cascada if c["estrategia"] != "original")
    print(f"Queries que gatillaron expansión: {cuantas_expandidas}/{n}")
    if cuantas_expandidas < n:
        print(
            f"Queries que se quedaron con la original: "
            f"{n - cuantas_expandidas}/{n} (top-1 sim >= {UMBRAL})"
        )


if __name__ == "__main__":
    main()
