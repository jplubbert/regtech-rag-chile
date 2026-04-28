"""Detector de anomalías de agrupación en casos LSC."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any


def _parse_fecha(s: str | date | None) -> date | None:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    return datetime.strptime(s, "%Y-%m-%d").date()


def _calcular_dia_habil_aprox(fecha: date, dias_habiles: int) -> date:
    """Aproximación rápida sin feriados — solo skip weekends."""
    cursor = fecha
    contados = 0
    while contados < dias_habiles:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            contados += 1
    return cursor


# Plazos aproximados (sin feriados; suficiente para detección de anomalías).
_PLAZO_PAGO_HABILES = 17  # 10 hábiles normales + 7 segunda restitución
_PLAZO_PAGO_CORRIDOS_APROX = 25  # ~17 hábiles ≈ 25 corridos
_DIFERENCIA_CASO_DUPLICADO = 14  # ~10 hábiles ≈ 14 corridos


def detectar_anomalias(
    casos: list[dict[str, Any]],
    hoy: str | date | None = None,
) -> list[dict[str, Any]]:
    """Aplica 5 reglas de detección sobre una lista de casos.

    Devuelve lista de anomalías. Cada anomalía:
      tipo, severidad, casos_involucrados, descripcion, accion_sugerida.
    """
    hoy = _parse_fecha(hoy) or date.today()
    anomalias: list[dict[str, Any]] = []

    # Indexar
    por_agrupacion: dict[str, list[dict]] = defaultdict(list)
    casos_por_rut: dict[str, list[dict]] = defaultdict(list)
    for c in casos:
        if c.get("id_agrupacion"):
            por_agrupacion[c["id_agrupacion"]].append(c)
        casos_por_rut[c["rut_usuario"]].append(c)

    # ----- Regla 1: RUTs distintos en una agrupación -----
    for agrup_id, lista in por_agrupacion.items():
        ruts = sorted({c["rut_usuario"] for c in lista})
        if len(ruts) > 1:
            anomalias.append({
                "tipo": "RUT_DISTINTOS_EN_AGRUPACION",
                "severidad": "alta",
                "casos_involucrados": [c["id_caso"] for c in lista],
                "descripcion": (
                    f"Agrupación {agrup_id} contiene RUTs distintos: {ruts}."
                ),
                "accion_sugerida": (
                    "Verificar con LSC si la agrupación está correctamente armada."
                ),
            })

    # ----- Regla 2: agrupaciones traslapadas mismo RUT -----
    for rut, lista in casos_por_rut.items():
        agrupaciones = sorted({
            c["id_agrupacion"] for c in lista if c.get("id_agrupacion")
        })
        if len(agrupaciones) < 2:
            continue
        # Calcular ventana [min_reclamo, max_pago_estimado] por agrupación
        ventanas: dict[str, tuple[date, date]] = {}
        for a in agrupaciones:
            casos_a = [
                c for c in lista
                if c.get("id_agrupacion") == a and c.get("fecha_reclamo")
            ]
            if not casos_a:
                continue
            fechas = [_parse_fecha(c["fecha_reclamo"]) for c in casos_a]
            min_f = min(fechas)
            max_f = max(fechas)
            pago_estimado = _calcular_dia_habil_aprox(max_f, _PLAZO_PAGO_HABILES)
            ventanas[a] = (min_f, pago_estimado)

        ag_keys = list(ventanas.keys())
        for i in range(len(ag_keys)):
            for j in range(i + 1, len(ag_keys)):
                a, b = ag_keys[i], ag_keys[j]
                ini_a, fin_a = ventanas[a]
                ini_b, fin_b = ventanas[b]
                # Traslape clásico de intervalos
                if ini_a <= fin_b and ini_b <= fin_a:
                    casos_a = [c["id_caso"] for c in lista if c.get("id_agrupacion") == a]
                    casos_b = [c["id_caso"] for c in lista if c.get("id_agrupacion") == b]
                    anomalias.append({
                        "tipo": "AGRUPACIONES_TRASLAPADAS_MISMO_RUT",
                        "severidad": "media",
                        "casos_involucrados": casos_a + casos_b,
                        "descripcion": (
                            f"RUT {rut} aparece en agrupaciones {a} ({ini_a}→{fin_a}) "
                            f"y {b} ({ini_b}→{fin_b}) cuyas ventanas se traslapan."
                        ),
                        "accion_sugerida": (
                            "Verificar con LSC si el segundo caso debió incluirse "
                            "en la agrupación existente."
                        ),
                    })

    # ----- Regla 3: caso individual cercano a una agrupación del mismo RUT -----
    for rut, lista in casos_por_rut.items():
        individuales = [c for c in lista if not c.get("id_agrupacion")]
        agrupados = [c for c in lista if c.get("id_agrupacion")]
        if not individuales or not agrupados:
            continue
        for ind in individuales:
            f_ind = _parse_fecha(ind.get("fecha_reclamo"))
            if not f_ind:
                continue
            for ag in agrupados:
                f_ag = _parse_fecha(ag.get("fecha_reclamo"))
                if not f_ag:
                    continue
                diff = abs((f_ind - f_ag).days)
                if diff < _DIFERENCIA_CASO_DUPLICADO:
                    anomalias.append({
                        "tipo": "CASO_INDIVIDUAL_DUPLICADO_CON_AGRUPACION",
                        "severidad": "media",
                        "casos_involucrados": [ind["id_caso"], ag["id_caso"]],
                        "descripcion": (
                            f"RUT {rut}: caso individual {ind['id_caso']} "
                            f"({f_ind}) y caso agrupado {ag['id_caso']} "
                            f"({f_ag}) con {diff} días corridos de diferencia."
                        ),
                        "accion_sugerida": (
                            "Verificar si el caso individual debería haber sido "
                            "incluido en la agrupación existente."
                        ),
                    })

    # ----- Regla 4: monto inconsistente en agrupación -----
    # Comparamos el monto total declarado por la agrupación contra la suma
    # de los montos individuales (de casos individuales del mismo RUT
    # reportados antes de la agrupación). Solo aplica si la agrupación
    # trae un campo `monto_declarado_total` o si todos los casos de la
    # misma agrupación tienen el mismo monto sumable.
    for agrup_id, lista in por_agrupacion.items():
        # Suma de los montos de la agrupación
        suma_agrupacion = sum(
            int(c.get("monto", 0) or 0) for c in lista
        )
        ruts_agrup = {c["rut_usuario"] for c in lista}
        if len(ruts_agrup) != 1:
            continue
        rut = next(iter(ruts_agrup))
        # Casos individuales del mismo RUT con fecha previa al primer reclamo
        f_min_agrup = min(
            _parse_fecha(c.get("fecha_reclamo"))
            for c in lista if c.get("fecha_reclamo")
        )
        previos = [
            c for c in casos_por_rut[rut]
            if not c.get("id_agrupacion")
            and _parse_fecha(c.get("fecha_reclamo"))
            and _parse_fecha(c.get("fecha_reclamo")) < f_min_agrup
        ]
        if not previos:
            continue
        suma_previos = sum(int(c.get("monto", 0) or 0) for c in previos)
        if suma_previos != suma_agrupacion and suma_previos > 0:
            anomalias.append({
                "tipo": "MONTO_INCONSISTENTE_AGRUPACION",
                "severidad": "alta",
                "casos_involucrados": (
                    [c["id_caso"] for c in previos]
                    + [c["id_caso"] for c in lista]
                ),
                "descripcion": (
                    f"Agrupación {agrup_id} (RUT {rut}) tiene monto total "
                    f"${suma_agrupacion:,} pero los casos individuales previos "
                    f"del mismo RUT suman ${suma_previos:,}."
                ),
                "accion_sugerida": (
                    "Verificar con LSC si la agrupación incluye/excluye casos "
                    "que deberían sumar al total."
                ),
            })

    # ----- Regla 5: pago vencido sin justificación -----
    for c in casos:
        f_reclamo = _parse_fecha(c.get("fecha_reclamo"))
        if not f_reclamo:
            continue
        f_limite = _calcular_dia_habil_aprox(f_reclamo, _PLAZO_PAGO_HABILES)
        if hoy > f_limite and c.get("estado") == "pendiente":
            dias_vencido = (hoy - f_limite).days
            anomalias.append({
                "tipo": "PAGO_VENCIDO_SIN_JUSTIFICACION",
                "severidad": "alta",
                "casos_involucrados": [c["id_caso"]],
                "descripcion": (
                    f"Caso {c['id_caso']} (RUT {c['rut_usuario']}, "
                    f"reclamo {f_reclamo}, plazo estimado {f_limite}) "
                    f"vencido hace {dias_vencido} días corridos. "
                    f"Estado actual: {c.get('estado')}."
                ),
                "accion_sugerida": (
                    "Escalar urgentemente con el equipo de pagos. Riesgo de "
                    "incumplimiento normativo."
                ),
            })

    return anomalias
