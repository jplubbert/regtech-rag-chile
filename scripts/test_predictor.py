"""Test del predictor de cronograma con 3 casos de prueba."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.predictor import predecir_cronograma

CASOS = [
    {
        "id_caso": "TEST-001",
        "rut_usuario": "11111111-1",
        "fecha_aviso": "2025-04-15",
        "fecha_reclamo": "2025-04-20",
        "monto_total_impugnado": 800_000,
        "producto_afectado": "01",
        "operacion_objeto": "03",
        "estado_denuncia": "01",
        "fecha_entrega_respaldo": "2025-04-22",
    },
    {
        "id_caso": "TEST-002",
        "rut_usuario": "22222222-2",
        "fecha_aviso": "2025-04-15",
        "fecha_reclamo": "2025-04-20",
        "monto_total_impugnado": 2_500_000,
        "producto_afectado": "01",
        "operacion_objeto": "04",
        "estado_denuncia": "02",
        "fecha_entrega_respaldo": None,
    },
    {
        "id_caso": "AGRUP-003",
        "rut_usuario": "33333333-3",
        "fecha_aviso": "2025-04-10",
        "fecha_reclamo": "2025-04-20",
        "monto_total_impugnado": 5_000_000,
        "producto_afectado": "03",
        "operacion_objeto": "03",
        "estado_denuncia": "01",
        "fecha_entrega_respaldo": "2025-04-21",
    },
]


def _formatear_clp(n: int) -> str:
    return f"${n:,}".replace(",", ".")


def render(out: dict) -> None:
    c = out["caso"]
    print("┌" + "─" * 78 + "┐")
    print(f"│ CASO: {c['id_caso']:<70} │")
    print(f"│ RUT: {c['rut_usuario']:<71} │")
    print("├" + "─" * 78 + "┤")
    print(
        f"│ aviso={c['fecha_aviso']}   reclamo={c['fecha_reclamo']}   "
        f"monto={_formatear_clp(c['monto'])}"
        + " " * max(0, 78 - 50 - len(_formatear_clp(c['monto'])))
        + "│"
    )
    print(
        f"│ UF={c.get('valor_uf_utilizado', '?')} (fecha {c.get('fecha_uf', '?')})  "
        f"umbral={_formatear_clp(c['umbral_clp_calculado'])} "
        f"({c['umbral_uf']} UF)"[:78].ljust(78)
        + "│"
    )
    print(
        f"│ supera_umbral={c['supera_umbral']}  "
        f"ATM/avance={c['es_atm_o_avance']}  "
        f"plazo={c['plazo_aplicable_dias_habiles']}d  "
        f"tipo_pago={c['tipo_pago']}"[:78].ljust(78)
        + "│"
    )
    print("└" + "─" * 78 + "┘")

    if out.get("validaciones"):
        print("\nVALIDACIONES:")
        for v in out["validaciones"]:
            estado = "✓" if v["cumple"] else "✗"
            detalles = ", ".join(
                f"{k}={vv}" for k, vv in v.items() if k not in ("regla", "cumple")
            )
            print(f"  {estado} [{v['regla']}] {detalles}")

    print("\nFECHAS CRÍTICAS:")
    for f in out["fechas_criticas"]:
        monto = (
            _formatear_clp(f["monto_aplicable"])
            if "monto_aplicable" in f
            else "—"
        )
        feriados = ", ".join(f["feriados_considerados"]) or "ninguno"
        print(f"  • [{f['id']}]  Campo E24 #{f['campo_e24']}")
        print(f"    {f['evento']}")
        print(
            f"    monto={monto}  "
            f"fecha_límite={f['fecha_limite']}  "
            f"({f['dias_habiles_calculados']} días hábiles, "
            f"feriados: {feriados})"
        )
        fl = f["fundamento_legal"]
        ref = fl.get("ley_referencia") or "—"
        sim = fl.get("similitud", 0.0)
        extracto = (fl.get("extracto") or "").replace("\n", " ")[:200]
        print(f"    fundamento → {ref}  (sim={sim:.3f})")
        print(f'      "{extracto}{"..." if len(fl.get("extracto", "")) > 200 else ""}"')
        print(f"    estado: {f['estado_actual']}")
        print()

    if out["alertas"]:
        print("ALERTAS:")
        for a in out["alertas"]:
            print(f"  ⚠ [{a['tipo']}] {a['mensaje']}")
        print()

    if out["escenarios_alternativos"]:
        print("ESCENARIOS ALTERNATIVOS (cómo cambia el cronograma si...):")
        for e in out["escenarios_alternativos"]:
            print(f"  ▸ {e['trigger']}")
            print(f"    fundamento: {e['fundamento']}")
            for mod in e["modificaciones_cronograma"]:
                print(f"      - {mod}")
        print()


def main() -> None:
    for i, caso_input in enumerate(CASOS, 1):
        print("\n" + "=" * 80)
        print(f"  CASO {i}: {caso_input['id_caso']}")
        print("=" * 80)
        out = predecir_cronograma(caso_input)
        render(out)


if __name__ == "__main__":
    main()
