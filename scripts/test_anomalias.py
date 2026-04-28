"""Test del detector de anomalías sobre dataset sintético."""

import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.anomalias import detectar_anomalias

CASOS_SINTETICOS = [
    # Caso normal individual
    {
        "id_caso": "C-001", "id_agrupacion": None, "rut_usuario": "11111111-1",
        "fecha_aviso": "2025-04-01", "fecha_reclamo": "2025-04-03",
        "monto": 500000, "estado": "pendiente",
    },
    # Anomalía 1: agrupación con RUTs distintos
    {
        "id_caso": "C-002", "id_agrupacion": "AGRUP-A", "rut_usuario": "22222222-2",
        "fecha_aviso": "2025-04-05", "fecha_reclamo": "2025-04-07",
        "monto": 800000, "estado": "pendiente",
    },
    {
        "id_caso": "C-003", "id_agrupacion": "AGRUP-A", "rut_usuario": "33333333-3",
        "fecha_aviso": "2025-04-06", "fecha_reclamo": "2025-04-08",
        "monto": 600000, "estado": "pendiente",
    },
    # Anomalía 2: agrupaciones traslapadas mismo RUT
    {
        "id_caso": "C-004", "id_agrupacion": "AGRUP-B", "rut_usuario": "44444444-4",
        "fecha_aviso": "2025-04-10", "fecha_reclamo": "2025-04-12",
        "monto": 1500000, "estado": "pendiente",
    },
    {
        "id_caso": "C-005", "id_agrupacion": "AGRUP-C", "rut_usuario": "44444444-4",
        "fecha_aviso": "2025-04-15", "fecha_reclamo": "2025-04-17",
        "monto": 900000, "estado": "pendiente",
    },
    # Anomalía 5: pago vencido (reclamo en marzo, hoy = abril)
    {
        "id_caso": "C-006", "id_agrupacion": None, "rut_usuario": "55555555-5",
        "fecha_aviso": "2025-03-01", "fecha_reclamo": "2025-03-03",
        "monto": 700000, "estado": "pendiente",
    },
]


_ICONO_SEVERIDAD = {"alta": "🔴", "media": "🟡", "baja": "⚪"}


def main() -> None:
    hoy = date(2025, 4, 25)
    print(f"Hoy simulado: {hoy}\n")
    print(f"Casos a evaluar: {len(CASOS_SINTETICOS)}\n")

    anomalias = detectar_anomalias(CASOS_SINTETICOS, hoy=hoy)
    print(f"=== {len(anomalias)} anomalía(s) detectada(s) ===\n")

    by_tipo: dict[str, int] = {}
    for a in anomalias:
        by_tipo[a["tipo"]] = by_tipo.get(a["tipo"], 0) + 1

    for tipo, n in sorted(by_tipo.items()):
        print(f"  • {tipo}: {n}")
    print()

    for i, a in enumerate(anomalias, 1):
        icono = _ICONO_SEVERIDAD.get(a["severidad"], "•")
        print("-" * 78)
        print(f"#{i}  {icono} [{a['severidad'].upper()}] {a['tipo']}")
        print(f"    casos: {', '.join(a['casos_involucrados'])}")
        print(f"    {a['descripcion']}")
        print(f"    → {a['accion_sugerida']}")
    print()


if __name__ == "__main__":
    main()
