"""Backfill de valores UF en la DB local desde mindicador.cl.

Uso:
    python scripts/actualizar_uf.py --desde 2024-01-01 --hasta 2025-04-28
    python scripts/actualizar_uf.py --hoy
    python scripts/actualizar_uf.py --ultimo-anio
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection
from core.predictor import _fetch_uf_remoto

SLEEP_ENTRE_REQUESTS_S = 0.1


def _parse_fecha(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _construir_rango(args: argparse.Namespace) -> tuple[date, date]:
    hoy = date.today()
    if args.hoy:
        return hoy, hoy
    if args.ultimo_anio:
        return hoy - timedelta(days=365), hoy
    if args.desde and args.hasta:
        return _parse_fecha(args.desde), _parse_fecha(args.hasta)
    raise SystemExit(
        "Uso: --hoy | --ultimo-anio | --desde YYYY-MM-DD --hasta YYYY-MM-DD"
    )


def _obtener_fechas_existentes(desde: date, hasta: date) -> set[date]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT fecha FROM valores_uf WHERE fecha BETWEEN %s AND %s",
            (desde, hasta),
        )
        return {row[0] for row in cur.fetchall()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--desde")
    parser.add_argument("--hasta")
    parser.add_argument("--hoy", action="store_true")
    parser.add_argument("--ultimo-anio", action="store_true", dest="ultimo_anio")
    args = parser.parse_args()

    desde, hasta = _construir_rango(args)
    print(f"Backfill UF desde {desde} hasta {hasta}")

    fechas_existentes = _obtener_fechas_existentes(desde, hasta)

    fechas_a_fetchear: list[date] = []
    cursor = desde
    while cursor <= hasta:
        fechas_a_fetchear.append(cursor)
        cursor += timedelta(days=1)

    total = len(fechas_a_fetchear)
    nuevos = ya_estaban = fallaron = 0
    print(f"Días en el rango: {total}\n")

    for i, fecha in enumerate(fechas_a_fetchear, start=1):
        if fecha in fechas_existentes:
            ya_estaban += 1
            continue
        result = _fetch_uf_remoto(fecha)
        if result is None:
            fallaron += 1
            print(f"  [{i:>3}/{total}] {fecha} — FALLÓ")
            continue
        valor, fecha_eff = result
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO valores_uf (fecha, valor) VALUES (%s, %s) "
                "ON CONFLICT (fecha) DO NOTHING",
                (fecha_eff, valor),
            )
        nuevos += 1
        if i <= 5 or i % 25 == 0 or i == total:
            print(f"  [{i:>3}/{total}] {fecha} → valor={valor} [nuevo]")
        time.sleep(SLEEP_ENTRE_REQUESTS_S)

    print(
        f"\nResumen:\n"
        f"  total días evaluados: {total}\n"
        f"  ya estaban en DB:     {ya_estaban}\n"
        f"  nuevos persistidos:   {nuevos}\n"
        f"  fallaron:             {fallaron}"
    )

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM valores_uf")
        total_db = cur.fetchone()[0]
    print(f"  total filas en valores_uf:    {total_db}")


if __name__ == "__main__":
    main()
