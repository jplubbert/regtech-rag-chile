"""Predictor de cronograma E24 reactivo (MVP).

Recibe un caso ya constituido (individual o agrupado por LSC) y devuelve:
  - Cronograma legal con fechas críticas (días hábiles bancarios chilenos).
  - Fundamentos legales recuperados vía RAG (Ley 20.009).
  - Escenarios alternativos (suspensión judicial, dolo/culpa grave, etc.).
  - Alertas operativas (umbral, ATM, denuncia pendiente, inconsistencias).

NO se ocupa de agrupar casos: asume que `monto_total_impugnado` ya viene
consolidado a nivel de caso/agrupación.
"""

import os
from datetime import date, datetime, timedelta
from typing import Any

import holidays
import httpx

from core.db import get_connection
from core.retrieval import buscar_en_cascada

# Configurable para tests de fallback (override vía MINDICADOR_URL_BASE).
MINDICADOR_URL_BASE = os.environ.get(
    "MINDICADOR_URL_BASE", "https://mindicador.cl/api/uf"
)

# --- Constantes legales ---------------------------------------------------

UMBRAL_UF = 35
# Fallback de último recurso si DB y red fallan.
VALOR_UF_FALLBACK_CLP = 38_500


def _buscar_uf_en_db(fecha: date) -> tuple[float, date] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT valor, fecha FROM valores_uf WHERE fecha = %s",
            (fecha,),
        )
        row = cur.fetchone()
    return (float(row[0]), row[1]) if row else None


def _buscar_uf_anterior_en_db(fecha: date) -> tuple[float, date] | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT valor, fecha FROM valores_uf WHERE fecha <= %s "
            "ORDER BY fecha DESC LIMIT 1",
            (fecha,),
        )
        row = cur.fetchone()
    return (float(row[0]), row[1]) if row else None


def _persistir_uf(fecha_eff: date, valor: float) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO valores_uf (fecha, valor) VALUES (%s, %s) "
            "ON CONFLICT (fecha) DO NOTHING",
            (fecha_eff, valor),
        )


def _fetch_uf_remoto(fecha: date) -> tuple[float, date] | None:
    """Consulta mindicador.cl. Devuelve (valor, fecha_efectiva) o None si falla."""
    url = f"{MINDICADOR_URL_BASE}/{fecha.strftime('%d-%m-%Y')}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        serie = resp.json().get("serie", []) or []
    except Exception as exc:
        print(f"  [WARN] fetch UF {fecha} falló: {exc}")
        return None
    if not serie:
        return None
    valor = float(serie[0]["valor"])
    fecha_str = serie[0].get("fecha", "")[:10]
    try:
        fecha_eff = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        fecha_eff = fecha
    return valor, fecha_eff


def obtener_uf(fecha: date) -> tuple[float, date]:
    """Devuelve (valor_uf, fecha_efectiva) con cascada DB → red → DB-anterior → fallback.

    1. Lee de tabla `valores_uf` (cache permanente local).
    2. Si no está, fetch a mindicador.cl, persiste e indexa.
    3. Si red falla, busca el último valor anterior disponible en DB.
    4. Último recurso: VALOR_UF_FALLBACK_CLP hardcoded.
    """
    cached = _buscar_uf_en_db(fecha)
    if cached is not None:
        return cached

    fetched = _fetch_uf_remoto(fecha)
    if fetched is not None:
        valor, fecha_eff = fetched
        _persistir_uf(fecha_eff, valor)
        return valor, fecha_eff

    anterior = _buscar_uf_anterior_en_db(fecha)
    if anterior is not None:
        print(
            f"  [INFO] Usando UF de {anterior[1]} "
            f"(último disponible anterior a {fecha})"
        )
        return anterior

    print(
        f"  [WARN] No hay valores UF en DB y la API no responde. "
        f"Usando fallback hardcoded {VALOR_UF_FALLBACK_CLP}."
    )
    return float(VALOR_UF_FALLBACK_CLP), fecha

PLAZO_RESTITUCION_NORMAL_DIAS_HABILES = 10
PLAZO_RESTITUCION_ATM_DIAS_HABILES = 15
PLAZO_SEGUNDA_RESTITUCION_DIAS_ADICIONALES = 7
PLAZO_DENUNCIA_DIAS_HABILES = 30

CODIGOS_OPERACION_ATM_AVANCE = {"04", "05"}


# --- Helpers fecha --------------------------------------------------------


def _parse_fecha(s: str | date | None) -> date | None:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    return datetime.strptime(s, "%Y-%m-%d").date()


def _calcular_dia_habil(
    fecha_inicio: date, dias_habiles: int
) -> tuple[date, list[date]]:
    """Suma N días hábiles bancarios chilenos a fecha_inicio.

    Excluye sábados, domingos y feriados nacionales (módulo `holidays`).
    Devuelve (fecha_final, feriados_atravesados).

    Fundamento: Ley 20.009 Art. 1 inc. final — los plazos de días hábiles
    no consideran sábados, domingos ni feriados bancarios (LGB Art. 38).
    """
    if dias_habiles <= 0:
        return fecha_inicio, []
    feriados_chile = holidays.country_holidays(
        "CL", years=range(fecha_inicio.year, fecha_inicio.year + 2)
    )
    cursor = fecha_inicio
    contados = 0
    feriados_atravesados: list[date] = []
    while contados < dias_habiles:
        cursor = cursor + timedelta(days=1)
        if cursor.weekday() >= 5:  # 5=sábado, 6=domingo
            continue
        if cursor in feriados_chile:
            feriados_atravesados.append(cursor)
            continue
        contados += 1
    return cursor, feriados_atravesados


# --- Fundamentos vía RAG --------------------------------------------------


def _obtener_fundamento(query: str) -> dict[str, Any]:
    """Llama buscar_en_cascada y devuelve {ley_referencia, extracto, sim}."""
    try:
        result = buscar_en_cascada(query, k=3)
    except Exception as exc:
        return {
            "ley_referencia": None,
            "extracto": f"(RAG error: {exc})",
            "similitud": 0.0,
        }
    chunks = result.get("chunks", []) or []
    if not chunks:
        return {
            "ley_referencia": None,
            "extracto": "(sin resultados)",
            "similitud": 0.0,
        }
    top = chunks[0]
    m = top["metadata"]
    if m.get("tipo") == "inciso" and m.get("documento") == "Ley 20.009":
        sufijo = f" {m['articulo_sufijo']}" if m.get("articulo_sufijo") else ""
        ley_ref = (
            f"Ley 20.009 Art. {m.get('articulo')}{sufijo} "
            f"inc. {m.get('inciso')}"
        )
    else:
        ley_ref = m.get("documento", "—")
    extracto = top.get("contenido", "")
    if len(extracto) > 350:
        extracto = extracto[:350] + "..."
    return {
        "ley_referencia": ley_ref,
        "extracto": extracto,
        "similitud": float(top.get("similitud", 0.0)),
    }


# --- Escenarios alternativos ---------------------------------------------


def _detectar_escenarios(caso: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "trigger": "Si el emisor solicita suspensión judicial (Campo 17 = 01)",
            "modificaciones_cronograma": [
                "Las fechas de los Campos 26 y 28 se reemplazan por '19000101'.",
                "Los pagos quedan suspendidos hasta resolución del JPL.",
                "Se deben completar Campos 17–25 con datos de la solicitud.",
            ],
            "fundamento": "Ley 20.009 Art. 5 bis",
        },
        {
            "trigger": "Si el JPL acoge la solicitud de suspensión (Campo 23 = 02)",
            "modificaciones_cronograma": [
                "El emisor tiene 10 días hábiles para presentar la demanda.",
                "Las restituciones siguen suspendidas hasta sentencia firme.",
                "Si la sentencia es a favor del usuario: 3 días hábiles desde notificación.",
            ],
            "fundamento": "Ley 20.009 Art. 5 bis inc. 4 y 6",
        },
        {
            "trigger": "Si se acredita dolo o culpa grave del usuario (Campo 33 = 02)",
            "modificaciones_cronograma": [
                "La suspensión queda firme: NO procede restitución.",
                "Campos 26–29 con ceros; Campo 34 con ceros.",
            ],
            "fundamento": "Ley 20.009 Art. 5 inc. 5 y Art. 5 ter",
        },
    ]


# --- Alertas operativas ---------------------------------------------------


def _generar_alertas(caso: dict[str, Any]) -> list[dict[str, Any]]:
    alertas: list[dict[str, Any]] = []
    if caso["supera_umbral"]:
        umbral = caso.get("umbral_clp_calculado", 0)
        alertas.append({
            "tipo": "umbral_excedido",
            "mensaje": (
                f"Caso supera umbral de {UMBRAL_UF} UF "
                f"(${umbral:,} CLP, valor UF {caso.get('valor_uf_utilizado', '?')}): "
                f"split en 2 pagos requerido."
            ),
        })
    if caso["es_atm_o_avance"]:
        alertas.append({
            "tipo": "operacion_atm_avance",
            "mensaje": (
                f"Operación ATM/avance: plazo extendido a "
                f"{PLAZO_RESTITUCION_ATM_DIAS_HABILES} días hábiles "
                f"(Art. 5 inc. 1 segunda parte)."
            ),
        })
    if caso.get("estado_denuncia") == "02":
        alertas.append({
            "tipo": "denuncia_pendiente",
            "mensaje": (
                "Estado denuncia=02 (pendiente): completar reclamo con nueves "
                "y volver a reportar el próximo periodo. Cronograma de pagos "
                "NO se gatilla hasta presentar respaldo."
            ),
        })
    if caso.get("estado_denuncia") == "03":
        alertas.append({
            "tipo": "denuncia_vencida_sin_respaldo",
            "mensaje": (
                "Estado denuncia=03 (vencido): si no se acompañó respaldo, "
                "NO procede restitución (Art. 4 inc. 4)."
            ),
        })
    fecha_aviso = _parse_fecha(caso.get("fecha_aviso"))
    fecha_reclamo = _parse_fecha(caso.get("fecha_reclamo"))
    if fecha_aviso and fecha_reclamo and fecha_aviso > fecha_reclamo:
        alertas.append({
            "tipo": "inconsistencia_fechas",
            "mensaje": (
                f"fecha_aviso ({fecha_aviso}) posterior a fecha_reclamo "
                f"({fecha_reclamo}). Verificar cronología."
            ),
        })
    return alertas


# --- Entrada pública ------------------------------------------------------


def predecir_cronograma(input_dict: dict[str, Any]) -> dict[str, Any]:
    """Recibe caso ya constituido, devuelve cronograma + escenarios + alertas."""
    fecha_aviso = _parse_fecha(input_dict.get("fecha_aviso"))
    fecha_reclamo = _parse_fecha(input_dict.get("fecha_reclamo"))
    monto = int(input_dict.get("monto_total_impugnado", 0) or 0)
    operacion_objeto = input_dict.get("operacion_objeto") or ""

    es_atm = operacion_objeto in CODIGOS_OPERACION_ATM_AVANCE
    plazo_dias = (
        PLAZO_RESTITUCION_ATM_DIAS_HABILES
        if es_atm
        else PLAZO_RESTITUCION_NORMAL_DIAS_HABILES
    )

    # UF dinámica via mindicador.cl (con cache + fallback).
    if fecha_reclamo:
        uf_valor, fecha_uf = obtener_uf(fecha_reclamo)
    else:
        uf_valor, fecha_uf = float(VALOR_UF_FALLBACK_CLP), None
    umbral_clp = int(round(UMBRAL_UF * uf_valor))

    supera_umbral = monto > umbral_clp
    monto_primer_pago = min(monto, umbral_clp)
    monto_segundo_pago = max(0, monto - umbral_clp)

    caso = {
        "id_caso": input_dict.get("id_caso"),
        "rut_usuario": input_dict.get("rut_usuario"),
        "fecha_aviso": str(fecha_aviso) if fecha_aviso else None,
        "fecha_reclamo": str(fecha_reclamo) if fecha_reclamo else None,
        "monto": monto,
        "umbral_uf": UMBRAL_UF,
        "valor_uf_utilizado": uf_valor,
        "fecha_uf": str(fecha_uf) if fecha_uf else None,
        "umbral_clp_calculado": umbral_clp,
        "supera_umbral": supera_umbral,
        "es_atm_o_avance": es_atm,
        "plazo_aplicable_dias_habiles": plazo_dias,
        "tipo_pago": "split_dos_pagos" if supera_umbral else "pago_unico",
        "estado_denuncia": input_dict.get("estado_denuncia"),
    }

    fechas_criticas: list[dict[str, Any]] = []

    # 1) Primera restitución (Campo 26)
    if fecha_reclamo:
        fecha_pago1, feriados1 = _calcular_dia_habil(fecha_reclamo, plazo_dias)
        fundamento_pago1 = _obtener_fundamento(
            "plazo cancelación cargos restitución fondos diez días hábiles "
            "primer inciso artículo 5"
        )
        fechas_criticas.append({
            "id": "primera_restitucion",
            "evento": (
                "Primera restitución (hasta umbral 35 UF)"
                if supera_umbral
                else "Restitución única (bajo umbral)"
            ),
            "monto_aplicable": monto_primer_pago,
            "fecha_limite": str(fecha_pago1),
            "dias_habiles_calculados": plazo_dias,
            "feriados_considerados": [str(f) for f in feriados1],
            "fundamento_legal": fundamento_pago1,
            "campo_e24": 26,
            "estado_actual": "pendiente",
        })

    # 2) Segunda restitución (Campo 28) — solo si supera umbral
    if supera_umbral and fecha_reclamo:
        fecha_pago2, feriados2 = _calcular_dia_habil(
            fecha_reclamo,
            plazo_dias + PLAZO_SEGUNDA_RESTITUCION_DIAS_ADICIONALES,
        )
        fundamento_pago2 = _obtener_fundamento(
            "segunda restitución monto sobre umbral siete días adicionales "
            "artículo 5 inciso 2"
        )
        fechas_criticas.append({
            "id": "segunda_restitucion",
            "evento": "Segunda restitución (monto sobre umbral)",
            "monto_aplicable": monto_segundo_pago,
            "fecha_limite": str(fecha_pago2),
            "dias_habiles_calculados": plazo_dias
            + PLAZO_SEGUNDA_RESTITUCION_DIAS_ADICIONALES,
            "dias_habiles_adicionales_sobre_primera": (
                PLAZO_SEGUNDA_RESTITUCION_DIAS_ADICIONALES
            ),
            "feriados_considerados": [str(f) for f in feriados2],
            "fundamento_legal": fundamento_pago2,
            "campo_e24": 28,
            "estado_actual": "pendiente",
        })

    # 3) Plazo de denuncia (Campo 8)
    if fecha_reclamo:
        fecha_denuncia, feriados_d = _calcular_dia_habil(
            fecha_reclamo, PLAZO_DENUNCIA_DIAS_HABILES
        )
        fundamento_denuncia = _obtener_fundamento(
            "plazo presentar denuncia carabineros respaldo treinta días"
        )
        fechas_criticas.append({
            "id": "plazo_denuncia",
            "evento": "Vencimiento plazo presentación respaldo de denuncia",
            "fecha_limite": str(fecha_denuncia),
            "dias_habiles_calculados": PLAZO_DENUNCIA_DIAS_HABILES,
            "feriados_considerados": [str(f) for f in feriados_d],
            "fundamento_legal": fundamento_denuncia,
            "campo_e24": 8,
            "estado_actual": (
                "cumplido"
                if input_dict.get("fecha_entrega_respaldo")
                else "pendiente"
            ),
        })

    validaciones = [
        {
            "regla": "pago_1_no_excede_umbral",
            "valor_pago_1": monto_primer_pago,
            "umbral_clp": umbral_clp,
            "cumple": monto_primer_pago <= umbral_clp,
        },
        {
            "regla": "suma_pagos_igual_monto_total",
            "monto_total": monto,
            "suma_pagos": monto_primer_pago + monto_segundo_pago,
            "cumple": (monto_primer_pago + monto_segundo_pago) == monto,
        },
        {
            "regla": "split_correcto_si_supera_umbral",
            "supera_umbral": supera_umbral,
            "tiene_segundo_pago": monto_segundo_pago > 0,
            "cumple": supera_umbral == (monto_segundo_pago > 0),
        },
    ]

    return {
        "caso": caso,
        "fechas_criticas": fechas_criticas,
        "validaciones": validaciones,
        "escenarios_alternativos": _detectar_escenarios(caso),
        "alertas": _generar_alertas(caso),
    }
