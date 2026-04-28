"""Funciones de chunking para indexar documentos normativos."""

import re
from typing import Any


def chunk_por_caracteres(
    texto: str,
    max_chars: int = 1500,
    overlap: int = 200,
) -> list[str]:
    """Chunking naive por caracteres con overlap.

    Útil como baseline. Para texto regulatorio estructurado conviene
    `chunk_por_secciones` y/o un chunker semántico.
    """
    if not texto or max_chars <= 0:
        return []
    if overlap >= max_chars:
        raise ValueError("overlap debe ser menor que max_chars")

    chunks: list[str] = []
    start = 0
    while start < len(texto):
        end = min(start + max_chars, len(texto))
        chunks.append(texto[start:end])
        if end == len(texto):
            break
        start = end - overlap
    return chunks


def chunk_por_secciones(
    texto: str,
    separador: str = "\n\n",
    min_chars: int = 100,
) -> list[str]:
    """Divide por separador y descarta secciones triviales."""
    return [
        seg.strip()
        for seg in texto.split(separador)
        if len(seg.strip()) >= min_chars
    ]


# ---------------------------------------------------------------------------
# Parser específico de Ley 20.009 (chunks por inciso + NOTAs).
# ---------------------------------------------------------------------------

_VERSION_LEY_20009 = "2024-05-30"

_RE_TITULO = re.compile(r"^Título\s+([IVXL]+)\s*$", re.IGNORECASE)
_RE_DISPOSICIONES = re.compile(r"^Disposiciones\s+finales\s*$", re.IGNORECASE)
_RE_ARTICULO = re.compile(
    r"^Artículo\s+(\d+)(?:\s+(bis|ter|quáter|quater))?\s*\.-\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)
_RE_NOTA = re.compile(r"^NOTA\b", re.IGNORECASE)
_RE_FIN_LEY = re.compile(r"^Y por cuanto", re.IGNORECASE)

_VALOR_ROMANO = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _romano_a_int(s: str) -> int:
    total = 0
    prev = 0
    for c in reversed(s.upper()):
        v = _VALOR_ROMANO.get(c, 0)
        total += -v if v < prev else v
        prev = v
    return total


def _meta_inciso(
    titulo_num: int | None,
    titulo_nombre: str | None,
    articulo_num: int | None,
    articulo_sufijo: str | None,
    articulo_es_bis: bool,
    inciso_idx: int,
) -> dict[str, Any]:
    return {
        "documento": "Ley 20.009",
        "version": _VERSION_LEY_20009,
        "tipo": "inciso",
        "titulo": titulo_num,
        "titulo_nombre": titulo_nombre,
        "articulo": articulo_num,
        "articulo_sufijo": articulo_sufijo,
        "articulo_es_bis": articulo_es_bis,
        "inciso": inciso_idx,
    }


def _es_marcador(linea: str) -> bool:
    """¿Esta línea inicia una sección estructural (no un inciso)?"""
    return bool(
        _RE_ARTICULO.match(linea)
        or _RE_TITULO.match(linea)
        or _RE_NOTA.match(linea)
        or _RE_DISPOSICIONES.match(linea)
        or _RE_FIN_LEY.match(linea)
    )


def parsear_ley_20009(texto: str) -> list[dict[str, Any]]:
    """Parsea la Ley 20.009 en chunks por inciso + chunks por cada NOTA.

    Estructura del archivo fuente:
    - Cada inciso es UNA línea con indent de 4 espacios.
    - Incisos consecutivos del mismo artículo NO tienen blank entre ellos.
    - Los blanks separan artículos, títulos y NOTAs.
    - "Título I" + su nombre van en líneas consecutivas (sin blank entre).
    - "NOTA" inicia su propia línea; el contenido va en la(s) línea(s)
      siguientes hasta blank o hasta el próximo marcador estructural.

    Decisiones:
    - Granularidad = inciso (1 línea ≈ 1 chunk).
    - El primer inciso de un artículo lleva el prefijo "Artículo N.-".
    - Sub-puntos a)-h) se consideran cada uno un inciso (si aparecen en
      líneas separadas, como en el archivo fuente).
    - "Disposiciones finales" actúa como título informal sin numeración.
    - El preámbulo (antes del primer artículo) y el cierre ("Y por
      cuanto...") se descartan.
    """
    chunks: list[dict[str, Any]] = []

    titulo_num: int | None = None
    titulo_nombre: str | None = None
    articulo_num: int | None = None
    articulo_sufijo: str | None = None
    articulo_es_bis = False
    inciso_idx = 0

    lines = texto.split("\n")
    i = 0
    while i < len(lines):
        clean = lines[i].strip()
        if not clean:
            i += 1
            continue

        # Cierre de la ley.
        if _RE_FIN_LEY.match(clean):
            break

        # Título numerado: nombre en la siguiente línea no-vacía
        # (a menos que esa siguiente línea sea otro marcador estructural).
        m = _RE_TITULO.match(clean)
        if m:
            titulo_num = _romano_a_int(m.group(1))
            titulo_nombre = None
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                cand = lines[j].strip()
                if not _es_marcador(cand):
                    titulo_nombre = cand
                    j += 1
            articulo_num = None
            articulo_sufijo = None
            articulo_es_bis = False
            inciso_idx = 0
            i = j
            continue

        # Disposiciones finales — título informal.
        if _RE_DISPOSICIONES.match(clean):
            titulo_num = None
            titulo_nombre = "Disposiciones finales"
            articulo_num = None
            articulo_sufijo = None
            articulo_es_bis = False
            inciso_idx = 0
            i += 1
            continue

        # NOTA — chunk aparte, ligado al artículo previo. El contenido es
        # las líneas siguientes hasta blank o próximo marcador.
        if _RE_NOTA.match(clean):
            j = i + 1
            content_lines: list[str] = []
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    break
                if _es_marcador(nxt):
                    break
                content_lines.append(nxt)
                j += 1
            contenido = " ".join(content_lines) if content_lines else clean
            chunks.append({
                "contenido": contenido,
                "metadata": {
                    "documento": "Ley 20.009",
                    "version": _VERSION_LEY_20009,
                    "tipo": "nota",
                    "articulo_relacionado": articulo_num,
                    "observacion": "explica origen/vigencia condicional",
                },
            })
            i = j
            continue

        # Artículo: primer inciso del artículo.
        m = _RE_ARTICULO.match(clean)
        if m:
            articulo_num = int(m.group(1))
            articulo_sufijo = (m.group(2) or "").lower() or None
            articulo_es_bis = (articulo_sufijo == "bis")
            inciso_idx = 1
            chunks.append({
                "contenido": clean,
                "metadata": _meta_inciso(
                    titulo_num, titulo_nombre,
                    articulo_num, articulo_sufijo, articulo_es_bis,
                    inciso_idx,
                ),
            })
            i += 1
            continue

        # Inciso continuación del artículo actual.
        if articulo_num is not None:
            inciso_idx += 1
            chunks.append({
                "contenido": clean,
                "metadata": _meta_inciso(
                    titulo_num, titulo_nombre,
                    articulo_num, articulo_sufijo, articulo_es_bis,
                    inciso_idx,
                ),
            })
        # else: preámbulo — descartado.
        i += 1

    return chunks


# ---------------------------------------------------------------------------
# Parser específico de E24 Registro 1 (Oficio Circular CMF 1381).
# ---------------------------------------------------------------------------

_VERSION_E24 = "2025-08-28"

# Header de campo: "N. NOMBRE EN MAYÚSCULAS [(con paréntesis)]"
_RE_E24_CAMPO_HEADER = re.compile(
    r"^(\d+)\.\s+([A-ZÁÉÍÓÚÑÜ()\s,\-]+?)\s*$"
)

# Header de tabla de códigos: "...| Código" o "...| Cód."
_RE_E24_TABLA_HEADER = re.compile(r"\|\s*(?:Código|Cód\.)\s*$", re.IGNORECASE)

# Fila de tabla de códigos: "descripción | NN" (NN puede tener 1-3 dígitos)
_RE_E24_TABLA_FILA = re.compile(r"^(.+?)\s*\|\s*(\d{1,3})\s*$")

# Reglas condicionales — dos formas:
#  (a) "Si en el Campo (N°)X ... el/al Código Y"
#  (b) "(Código(s) Y del Campo X)"  o  "(Códigos Y y Z del Campo X)"
_RE_E24_REGLA_DIRECTA = re.compile(
    r"Si en el Campo\s*(?:N°)?\s*(\d+)\b"
    r"(?:[^.]*?)"
    r"[Cc]ódigo\s+(\d+)",
)
_RE_E24_REGLA_INVERSA = re.compile(
    r"\(\s*Códigos?\s+(\d+(?:\s+y\s+\d+)?)\s+del\s+Campo\s*(?:N°)?\s*(\d+)\s*\)",
    re.IGNORECASE,
)

# Regla "los campos siguientes" — afecta a todos los campos posteriores
# desde campo_actual+1 hasta el final del Registro 1, opcionalmente con
# excepciones por rango o singulares.
# Lookahead negativo en "los siguientes": evita matchear cuando introduce
# tablas ("los siguientes códigos:") o enumeraciones ("los siguientes
# casos/incisos/puntos/párrafos").
_RE_E24_CAMPOS_SIGUIENTES = re.compile(
    r"\b(?:"
    r"campos?\s+siguientes|"
    r"siguientes\s+campos?|"
    r"los\s+siguientes(?!\s+(?:códigos?|incisos?|puntos?|párrafos?|literales?|casos?|supuestos?))"
    r")\b",
    re.IGNORECASE,
)

# "este campo y los siguientes" / "este, y los Campos siguientes" — incluye
# al campo actual en la lista de afectados.
_RE_E24_INCLUYE_ESTE = re.compile(
    r"\beste(?:\s+campo)?\s*(?:,\s*)?y\s+(?:todos\s+)?los\s+(?:campos?\s+)?siguientes",
    re.IGNORECASE,
)

# Excepciones por rango: "Campos n°9 al 16", "26° al 29°", "n°9 a 16"
_RE_E24_EXCEPCION_RANGO = re.compile(
    r"\b(?:campos?\s*)?[Nn]?°?\s*(\d+)°?\s+(?:al?|a)\s+(?:[Nn]?°?\s*)?(\d+)°?\b"
)

# Excepción singular: "Campo N°20", "Campo 26"
_RE_E24_EXCEPCION_SINGULAR = re.compile(
    r"\b[Cc]ampos?\s*[Nn]?°?\s*(\d+)\b"
)

# Cláusula que abre una zona de excepciones — capturamos lo que sigue
# hasta el siguiente punto-y-mayúscula.
_RE_E24_CLAUSULA_EXCEPCION = re.compile(
    r"(?:excepto(?:\s+que)?|con\s+excepción\s+de|salvo)([^.]*)",
    re.IGNORECASE,
)

# Código intra-campo: "En caso de seleccionar la opción/el Código X",
# "Se debe informar con el Código X cuando..."
_RE_E24_CODIGO_INTRA = re.compile(
    r"(?:[Ee]n\s+caso\s+de\s+seleccionar\s+(?:la\s+opción|el\s+[Cc]ódigo)|"
    r"[Ss]e\s+debe\s+informar\s+con\s+el\s+[Cc]ódigo)\s+(\d+)",
    re.IGNORECASE,
)

# Marcadores de bloque
_E24_MARCA_DEFINICION = "Definición de términos"
_E24_MARCA_REGISTRO_1 = "Registro 1 que contiene"
_E24_MARCA_REGISTRO_2 = "Registro 2 que contiene"
_E24_MARCA_TRANSITORIEDAD = "Transitoriedad legal:"


def _meta_e24_base() -> dict[str, Any]:
    return {"documento": "E24", "version": _VERSION_E24, "registro": 1}


def _extraer_filas_tabla(
    lineas: list[str], inicio: int
) -> tuple[list[tuple[str, str]], int]:
    """Si lineas[inicio] es header de tabla, devuelve (filas, idx_post_tabla)."""
    if not _RE_E24_TABLA_HEADER.search(lineas[inicio]):
        return [], inicio
    filas: list[tuple[str, str]] = []
    j = inicio + 1
    while j < len(lineas):
        m = _RE_E24_TABLA_FILA.match(lineas[j])
        if m:
            filas.append((m.group(1).strip(), m.group(2).strip()))
            j += 1
        else:
            # Si la línea es vacía, la salteo (puede haber espacios entre filas)
            if not lineas[j].strip():
                j += 1
                if j < len(lineas) and _RE_E24_TABLA_FILA.match(lineas[j]):
                    continue
                break
            break
    return filas, j


def _detectar_reglas_en_linea(linea: str, campo_actual: int) -> list[dict[str, Any]]:
    """Devuelve list de dicts con depende_de_campo + depende_de_codigo."""
    out: list[dict[str, Any]] = []
    for m in _RE_E24_REGLA_DIRECTA.finditer(linea):
        out.append({
            "depende_de_campo": int(m.group(1)),
            "depende_de_codigo": m.group(2).zfill(2),
        })
    for m in _RE_E24_REGLA_INVERSA.finditer(linea):
        codigos = re.findall(r"\d+", m.group(1))
        for c in codigos:
            out.append({
                "depende_de_campo": int(m.group(2)),
                "depende_de_codigo": c.zfill(2),
            })
    return out


def _detectar_excepciones(linea: str) -> set[int]:
    """Devuelve los campos excluidos por cláusulas 'excepto/con excepción de'."""
    excluidos: set[int] = set()
    for m_exc in _RE_E24_CLAUSULA_EXCEPCION.finditer(linea):
        cola = m_exc.group(1)
        # Rangos primero (consumen "n°9 al 16")
        for m_r in _RE_E24_EXCEPCION_RANGO.finditer(cola):
            inicio, fin = int(m_r.group(1)), int(m_r.group(2))
            if 1 <= inicio <= 34 and inicio <= fin <= 34:
                excluidos.update(range(inicio, fin + 1))
        # Singulares dentro del mismo cola (no se solapan al ser set)
        for m_s in _RE_E24_EXCEPCION_SINGULAR.finditer(cola):
            n = int(m_s.group(1))
            if 1 <= n <= 34:
                excluidos.add(n)
    return excluidos


def _detectar_reglas_globales(
    linea: str, campo_actual: int
) -> list[dict[str, Any]]:
    """Reglas tipo 'los campos siguientes' (con/sin excepciones).

    Devuelve uno o cero dicts con depende_de_campo + depende_de_codigo +
    afecta_global. Identifica el discriminador así:
      - Si la línea tiene "Si en el Campo N°X" → discriminador = X.
      - Si tiene "En caso de seleccionar el Código Y" → discriminador =
        campo_actual con código Y.
      - Si no tiene ninguno → discriminador = campo_actual con código None.
    """
    if not _RE_E24_CAMPOS_SIGUIENTES.search(linea):
        return []

    excluidos = _detectar_excepciones(linea)
    incluye_actual = bool(_RE_E24_INCLUYE_ESTE.search(linea))
    inicio_rango = campo_actual if incluye_actual else campo_actual + 1
    afecta_global = sorted(
        n for n in range(inicio_rango, 35) if n not in excluidos
    )
    if not afecta_global:
        return []

    inter = _RE_E24_REGLA_DIRECTA.search(linea)
    if inter:
        return [{
            "depende_de_campo": int(inter.group(1)),
            "depende_de_codigo": inter.group(2).zfill(2),
            "afecta_global": afecta_global,
        }]

    intra = _RE_E24_CODIGO_INTRA.search(linea)
    if intra:
        return [{
            "depende_de_campo": campo_actual,
            "depende_de_codigo": intra.group(1).zfill(2),
            "afecta_global": afecta_global,
        }]

    return [{
        "depende_de_campo": campo_actual,
        "depende_de_codigo": None,
        "afecta_global": afecta_global,
    }]


def _extraer_accion(linea: str) -> str:
    """Heurística breve: del primer match de regla, devuelve el texto que sigue."""
    m = _RE_E24_REGLA_DIRECTA.search(linea)
    if m:
        cola = linea[m.end():].strip(" ,.;:")
        # Cortar en el primer punto seguido de mayúscula o nueva oración.
        cola = re.split(r"\.\s+(?=[A-ZÁÉÍÓÚÑ])", cola, maxsplit=1)[0]
        return cola.strip()
    m = _RE_E24_REGLA_INVERSA.search(linea)
    if m:
        cola = linea[m.end():].strip(" ,.;:")
        cola = re.split(r"\.\s+(?=[A-ZÁÉÍÓÚÑ])", cola, maxsplit=1)[0]
        return cola.strip()
    return ""


def _parsear_un_campo(
    lineas_campo: list[str], num: int, nombre: str
) -> list[dict[str, Any]]:
    """Procesa un campo: descripción + tabla de códigos + reglas condicionales."""
    chunks: list[dict[str, Any]] = []

    # Descripción: las líneas hasta (la primera tabla) o (la primera regla
    # condicional) o (fin del bloque) — lo que ocurra antes.
    idx_corte = len(lineas_campo)
    idx_tabla_inicio = -1
    for i, linea in enumerate(lineas_campo):
        if _RE_E24_TABLA_HEADER.search(linea):
            idx_corte = i
            idx_tabla_inicio = i
            break
        if _detectar_reglas_en_linea(linea, num):
            idx_corte = i
            break
        if _detectar_reglas_globales(linea, num):
            idx_corte = i
            break

    descripcion = "\n".join(l for l in lineas_campo[:idx_corte] if l.strip()).strip()
    descripcion_completa = (
        f"{num}. {nombre}\n{descripcion}".strip()
        if descripcion
        else f"{num}. {nombre}"
    )
    chunks.append({
        "contenido": descripcion_completa,
        "metadata": {
            **_meta_e24_base(),
            "tipo": "campo_descripcion",
            "campo_numero": num,
            "campo_nombre": nombre,
            # `formato`, `es_discriminador`, `afecta_a` se llenan después.
        },
    })

    # Tabla de códigos
    idx_post_tabla = idx_corte
    if idx_tabla_inicio != -1:
        filas, idx_post_tabla = _extraer_filas_tabla(lineas_campo, idx_tabla_inicio)
        for valor, codigo in filas:
            chunks.append({
                "contenido": (
                    f"Campo {num} ({nombre}) — Código {codigo}: {valor}"
                ),
                "metadata": {
                    **_meta_e24_base(),
                    "tipo": "codigo",
                    "campo_numero": num,
                    "campo_nombre": nombre,
                    "codigo": codigo,
                    "valor_descripcion": valor,
                },
            })

    # Reglas condicionales en lo restante
    for linea in lineas_campo[idx_post_tabla:]:
        clean = linea.strip()
        if not clean:
            continue

        # (1) Reglas inter-campo / inversas existentes
        reglas = _detectar_reglas_en_linea(clean, num)
        if reglas:
            accion = _extraer_accion(clean)
            seen: set[tuple[int, str]] = set()
            for r in reglas:
                key = (r["depende_de_campo"], r["depende_de_codigo"])
                if key in seen:
                    continue
                seen.add(key)
                chunks.append({
                    "contenido": clean,
                    "metadata": {
                        **_meta_e24_base(),
                        "tipo": "regla_condicional",
                        "campo_numero": num,
                        "depende_de_campo": r["depende_de_campo"],
                        "depende_de_codigo": r["depende_de_codigo"],
                        "accion": accion or None,
                    },
                })

        # (2) Reglas globales tipo "los campos siguientes"
        for rg in _detectar_reglas_globales(clean, num):
            chunks.append({
                "contenido": clean,
                "metadata": {
                    **_meta_e24_base(),
                    "tipo": "regla_condicional",
                    "campo_numero": num,
                    "depende_de_campo": rg["depende_de_campo"],
                    "depende_de_codigo": rg["depende_de_codigo"],
                    "afecta_global": rg["afecta_global"],
                    "accion": "regla 'campos siguientes' con o sin excepciones",
                },
            })

    return chunks


def _enriquecer_discriminadores(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Llena `es_discriminador` y `afecta_a` en los chunks campo_descripcion.

    Considera dos fuentes de evidencia:
      (a) reglas inter-campo (depende_de_campo, campo_numero) → afecta {campo_numero}
      (b) reglas globales con afecta_global → afecta a la lista entera
    Ambas se acumulan en `afecta_map` y la unión final se asigna al
    discriminador (excluyéndose a sí mismo).
    """
    afecta_map: dict[int, set[int]] = {}
    for c in chunks:
        m = c["metadata"]
        if m.get("tipo") != "regla_condicional":
            continue
        dep = m.get("depende_de_campo")
        if dep is None:
            continue
        afecta_global = m.get("afecta_global")
        if afecta_global:
            afecta_map.setdefault(dep, set()).update(
                n for n in afecta_global if n != dep
            )
        else:
            actual = m.get("campo_numero")
            if actual and dep != actual:
                afecta_map.setdefault(dep, set()).add(actual)

    for c in chunks:
        m = c["metadata"]
        if m.get("tipo") != "campo_descripcion":
            continue
        n = m.get("campo_numero")
        afecta = sorted(afecta_map.get(n, set()))
        m["es_discriminador"] = bool(afecta)
        m["afecta_a"] = afecta
    return chunks


def parsear_e24_registro1(texto: str) -> list[dict[str, Any]]:
    """Parsea el Registro 1 del E24 en chunks de granularidad mínima.

    Tipos generados:
      - contexto_general (preambulo / definicion_general / transitoriedad_legal)
      - campo_descripcion (uno por campo del Registro 1)
      - codigo (uno por fila de tabla de códigos)
      - regla_condicional (uno por dependencia inter-campo detectada)

    Tras la extracción, una segunda pasada llena `es_discriminador` y
    `afecta_a` en cada `campo_descripcion` basándose en quién lo referencia.
    """
    chunks: list[dict[str, Any]] = []

    # Localizar marcas
    idx_def = texto.find(_E24_MARCA_DEFINICION)
    if idx_def == -1:
        raise ValueError(
            f"No se encontró '{_E24_MARCA_DEFINICION}' en el texto del E24."
        )
    idx_reg2 = texto.find(_E24_MARCA_REGISTRO_2)
    fin_campos = idx_reg2 if idx_reg2 != -1 else len(texto)
    idx_reg1 = texto.find(_E24_MARCA_REGISTRO_1)

    # --- Pre-bloque: contexto general ---
    pre_texto = texto[:idx_reg1].strip() if idx_reg1 != -1 else texto[:idx_def].strip()
    if pre_texto:
        chunks.append({
            "contenido": pre_texto,
            "metadata": {
                "documento": "E24",
                "version": _VERSION_E24,
                "tipo": "contexto_general",
                "seccion": "preambulo",
            },
        })

    # --- Intro Registro 1 + transitoriedad ---
    if idx_reg1 != -1:
        intro_texto = texto[idx_reg1:idx_def].strip()
        idx_trans = intro_texto.find(_E24_MARCA_TRANSITORIEDAD)
        if idx_trans != -1:
            definicion_general = intro_texto[:idx_trans].strip()
            transitoriedad = intro_texto[idx_trans:].strip()
            if definicion_general:
                chunks.append({
                    "contenido": definicion_general,
                    "metadata": {
                        "documento": "E24",
                        "version": _VERSION_E24,
                        "tipo": "contexto_general",
                        "seccion": "definicion_general",
                    },
                })
            if transitoriedad:
                chunks.append({
                    "contenido": transitoriedad,
                    "metadata": {
                        "documento": "E24",
                        "version": _VERSION_E24,
                        "tipo": "contexto_general",
                        "seccion": "transitoriedad_legal",
                    },
                })
        else:
            chunks.append({
                "contenido": intro_texto,
                "metadata": {
                    "documento": "E24",
                    "version": _VERSION_E24,
                    "tipo": "contexto_general",
                    "seccion": "definicion_general",
                },
            })

    # --- Bloque de campos ---
    bloque = texto[idx_def + len(_E24_MARCA_DEFINICION):fin_campos]
    lineas = bloque.split("\n")

    # Localizar todos los headers de campo
    headers: list[tuple[int, int, str]] = []  # (idx_linea, num, nombre)
    for i, linea in enumerate(lineas):
        m = _RE_E24_CAMPO_HEADER.match(linea.strip())
        if m and not _RE_E24_TABLA_HEADER.search(linea):
            num = int(m.group(1))
            nombre = m.group(2).strip()
            # Filtro defensivo: descartar matches falsos (ej. "1 Avisos…")
            if 1 <= num <= 100 and len(nombre) >= 3:
                headers.append((i, num, nombre))

    # Procesar cada campo entre headers consecutivos
    for k, (idx_linea, num, nombre) in enumerate(headers):
        fin = headers[k + 1][0] if k + 1 < len(headers) else len(lineas)
        lineas_campo = lineas[idx_linea + 1:fin]
        chunks.extend(_parsear_un_campo(lineas_campo, num, nombre))

    return _enriquecer_discriminadores(chunks)

