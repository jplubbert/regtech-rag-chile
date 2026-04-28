"""Query expansion para retrieval sobre Ley 20.009.

Dos modos:
- 'glosario' (default): fuerza al LLM a usar los términos canónicos de la
  Ley 20.009 (e.g. "emisor", "medio de pago", "claves"). Mejor recall.
- 'generica': reformulación libre a español jurídico. Baseline débil que
  tiende a agregar términos genéricos no presentes en la ley.
"""

from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

MODEL = "gpt-4o-mini"

# Glosario coloquial → canónico. KEY = término que el usuario probablemente
# use; VALUE = el término literal que aparece en la Ley 20.009.
GLOSARIO_LEY_20009: dict[str, str] = {
    # Sujetos
    "banco / entidad financiera / institución bancaria": "emisor",
    "cliente / titular": "usuario",
    "tarjeta de crédito / débito / bancaria": "medio de pago",
    # Acciones del usuario
    "robaron / hurtaron / extraviaron": "hurto, robo o extravío",
    "presentar denuncia / reclamar": "dar aviso al emisor",
    "claves / contraseña": "claves",
    # Acciones del banco
    "devolver dinero": "restitución de fondos o cancelación de cargos",
    "bloquear tarjeta": "bloqueo del medio de pago",
    "no responsabilizarse": "presunción de dolo o culpa grave del usuario",
    # Procedimientos
    "denunciar a la policia": "denuncia ante Ministerio Público, Carabineros de Chile o Policía de Investigaciones",
    "ir a tribunales": "Juzgado de Policía Local",
    "pedir que no se devuelva": "solicitud de suspensión",
    # Conceptos legales
    "responsabilidad del cliente": "dolo o culpa grave del usuario",
    "monto pequeño / monto grande": "umbral establecido en el reglamento",
    "verificación de seguridad": "autenticación reforzada",
}


def _formatear_glosario() -> str:
    return "\n".join(f"- {k} → {v}" for k, v in GLOSARIO_LEY_20009.items())


_PROMPT_GLOSARIO = """\
Sos un asistente especializado en la Ley 20.009 sobre fraude bancario
chileno. Tu trabajo es reformular preguntas de usuarios SOLAMENTE
traduciendo vocabulario coloquial a vocabulario canónico de la ley.

REGLAS ESTRICTAS:
1. Mantené la estructura sintáctica EXACTA de la pregunta original. Si
   era pregunta, sigue siendo pregunta. Si tenía "qué hago", "cuándo",
   "cómo", "por qué", "en qué casos" — esos verbos interrogativos quedan
   IGUAL.
2. Traducí ÚNICAMENTE las palabras que aparecen en el glosario. Todo lo
   demás queda igual.
3. NO cambies frases completas. NO conviertas preguntas en frases
   nominales. NO resumas ni acortes.
4. Si la pregunta ya usa vocabulario canónico, devolvela EXACTAMENTE
   igual.
5. Devolvé SOLO la pregunta reformulada, sin explicaciones.

GLOSARIO DE TÉRMINOS CANÓNICOS:
{glosario}

Ejemplos correctos (preservan estructura):
- "¿Qué hago si me roban la tarjeta?" → "¿Qué hago si sufro hurto, robo o extravío del medio de pago?"
- "El banco debe devolverme la plata" → "El emisor debe restituirme los fondos"
- "¿Cuándo el banco no es responsable?" → "¿Cuándo hay presunción de dolo o culpa grave del usuario?"
- "Plazo para presentar denuncia ante carabineros" → "Plazo para presentar denuncia ante Carabineros de Chile"

Ejemplos INCORRECTOS (alteran estructura):
- "¿Qué hago si me roban la tarjeta?" → "Hurto o robo del medio de pago" ✗ (perdió el verbo de acción)
- "¿Cuándo el banco no es responsable?" → "Presunción de dolo o culpa grave" ✗ (perdió la pregunta)

DIRECCIONALIDAD ESTRICTA:
El glosario es UNIDIRECCIONAL: traduce de coloquial a canónico, NUNCA de
canónico a coloquial.
- Si la pregunta usa "autenticación reforzada", dejala así. NO la cambies
  a "verificación de seguridad".
- Si la pregunta usa "emisor", dejala así. NO la cambies a "banco" ni a
  "institución financiera".
- Si la pregunta usa "medio de pago", dejala así. NO la cambies a
  "tarjeta".
- Si la pregunta usa "usuario", dejala así. NO la cambies a "cliente" ni
  "titular".
- Si la pregunta usa "hurto, robo o extravío", dejala así. NO la cambies
  a "robaron" ni "hurtaron".

Solo aplicá traducciones en la dirección coloquial → canónico.
""".format(glosario=_formatear_glosario())


_PROMPT_GENERICO = """\
Sos un asistente especializado en normativa bancaria chilena. Te llegará
una pregunta de un usuario y debés reformularla usando el vocabulario
técnico-legal apropiado para buscar en la Ley 20.009 sobre fraude bancario.

Reglas:
- Reemplazá lenguaje coloquial por términos legales: 'me roban' → 'hurto,
  robo o extravío'
- Expandí abreviaciones y siglas
- Agregá sinónimos legales relevantes
- NO inventes información que no esté en la pregunta original
- Devolvé SOLO la query reformulada, sin explicaciones ni preámbulos
- Mantenela concisa (máximo 30 palabras)
"""


def _client() -> OpenAI:
    return OpenAI()


def expandir_query(query: str, modo: str = "glosario") -> str:
    """Reformula la query a vocabulario legal.

    modo='glosario': usa el glosario canónico de la Ley 20.009 (default).
    modo='generica': reformulación libre a español jurídico.
    """
    if modo == "glosario":
        sistema = _PROMPT_GLOSARIO
        temperatura = 0.1
    elif modo == "generica":
        sistema = _PROMPT_GENERICO
        temperatura = 0.2
    else:
        raise ValueError(f"modo desconocido: {modo!r}")

    resp = _client().chat.completions.create(
        model=MODEL,
        temperature=temperatura,
        messages=[
            {"role": "system", "content": sistema},
            {"role": "user", "content": query},
        ],
    )
    return resp.choices[0].message.content.strip()
