"""Benchmark comparativo: retrieval con 3 estrategias de query expansion.

Para cada una de 8 queries variadas mide top-1 sim y rank de la respuesta
esperada bajo:
  (sin) query original sin expansión
  (gen) expansión genérica (LLM libre)
  (glo) expansión con glosario canónico de la Ley 20.009
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.query_expansion import expandir_query
from core.retrieval import buscar_similares

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


def evaluar(textos: list[tuple[dict, str]]) -> list[dict]:
    out = []
    for q, texto in textos:
        chunks = buscar_similares(texto, k=3, expandir=False)
        rank = primer_rank(chunks, q["esperado"])
        out.append({
            "n": q["n"],
            "tag": q["tag"],
            "query": q["query"],
            "top1_sim": chunks[0]["similitud"] if chunks else 0.0,
            "rank": rank,
        })
    return out


def _rank_str(r: int | None) -> str:
    return "miss" if r is None else str(r)


def main() -> None:
    # 1) Generar expansiones (16 LLM calls = 8 queries × 2 modos).
    print("=" * 100)
    print("EXPANSIONES POR QUERY")
    print("=" * 100)
    for q in QUERIES:
        q["exp_gen"] = expandir_query(q["query"], modo="generica")
        q["exp_glo"] = expandir_query(q["query"], modo="glosario")
        print(f"\nQ{q['n']}  [{q['tag']}]")
        print(f"  original:  {q['query']}")
        print(f"  genérica:  {q['exp_gen']}")
        print(f"  glosario:  {q['exp_glo']}")

    # 2) Tres benchmarks (24 retrieval calls = 8 × 3).
    sin = evaluar([(q, q["query"])    for q in QUERIES])
    gen = evaluar([(q, q["exp_gen"])  for q in QUERIES])
    glo = evaluar([(q, q["exp_glo"])  for q in QUERIES])

    # 3) Tabla comparativa.
    print("\n" + "=" * 110)
    print("COMPARATIVA")
    print("=" * 110)
    header = (
        f"{'Q':>2}  {'TIPO':<28}  "
        f"{'sim/sin':>7} {'r/sin':>5}    "
        f"{'sim/gen':>7} {'r/gen':>5}    "
        f"{'sim/glo':>7} {'r/glo':>5}    "
        f"veredicto glo vs sin"
    )
    print(header)
    print("-" * 110)

    glo_mejor_que_sin = 0
    glo_peor_que_sin = 0
    glo_igual_que_sin = 0
    glo_mejor_que_gen = 0

    for s, g, lo in zip(sin, gen, glo):
        s_tier = (s["rank"] is None, s["rank"] or 99)
        g_tier = (g["rank"] is None, g["rank"] or 99)
        lo_tier = (lo["rank"] is None, lo["rank"] or 99)

        if lo_tier < s_tier:
            verdict = "↑ ganada vs sin"
            glo_mejor_que_sin += 1
        elif lo_tier > s_tier:
            verdict = "↓ perdida vs sin"
            glo_peor_que_sin += 1
        else:
            d = lo["top1_sim"] - s["top1_sim"]
            if d > 0.02:
                verdict = "↑ sim mejor"
                glo_mejor_que_sin += 1
            elif d < -0.02:
                verdict = "↓ sim peor"
                glo_peor_que_sin += 1
            else:
                verdict = "= neutra"
                glo_igual_que_sin += 1

        if lo_tier < g_tier or (
            lo_tier == g_tier and lo["top1_sim"] > g["top1_sim"] + 0.02
        ):
            glo_mejor_que_gen += 1

        print(
            f"{s['n']:>2}  {s['tag'][:28]:<28}  "
            f"{s['top1_sim']:>7.3f} {_rank_str(s['rank']):>5}    "
            f"{g['top1_sim']:>7.3f} {_rank_str(g['rank']):>5}    "
            f"{lo['top1_sim']:>7.3f} {_rank_str(lo['rank']):>5}    "
            f"{verdict}"
        )

    # 4) Resumen.
    print("\n" + "=" * 110)
    print("RESUMEN")
    print("=" * 110)
    n = len(QUERIES)
    top1 = lambda data: sum(1 for x in data if x["rank"] == 1)
    top3 = lambda data: sum(1 for x in data if x["rank"] is not None)

    print(f"{'':<24}{'sin exp':>12}{'gen':>12}{'glosario':>12}")
    print(
        f"{'top-1 acierto:':<24}"
        f"{top1(sin):>4}/{n:<6}  {top1(gen):>4}/{n:<6}  {top1(glo):>4}/{n:<6}"
    )
    print(
        f"{'top-3 acierto:':<24}"
        f"{top3(sin):>4}/{n:<6}  {top3(gen):>4}/{n:<6}  {top3(glo):>4}/{n:<6}"
    )
    print(
        f"{'top-1 sim promedio:':<24}"
        f"{sum(s['top1_sim'] for s in sin)/n:>10.3f}  "
        f"{sum(s['top1_sim'] for s in gen)/n:>10.3f}  "
        f"{sum(s['top1_sim'] for s in glo)/n:>10.3f}"
    )
    print()
    print("Glosario vs sin expansión:")
    print(f"  mejoradas: {glo_mejor_que_sin}/{n}")
    print(f"  neutras:   {glo_igual_que_sin}/{n}")
    print(f"  empeoradas:{glo_peor_que_sin}/{n}")
    print(f"Glosario vs expansión genérica:")
    print(f"  glosario gana: {glo_mejor_que_gen}/{n}")


if __name__ == "__main__":
    main()
