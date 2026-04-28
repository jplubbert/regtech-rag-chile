"""Generación de respuestas estructuradas en JSON sobre top-K chunks.

Cierra el ciclo del RAG: query → buscar_en_cascada → LLM final → JSON
estructurado con respuesta + citas + confianza + advertencias. La salida
está pensada para alimentar otros sistemas, no para chat directo, así
que prioriza precisión, trazabilidad y ausencia de alucinaciones.
"""

import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from core.retrieval import buscar_en_cascada

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

MODEL = "gpt-4o-mini"
TEMPERATURA = 0.1

SYSTEM_PROMPT = """\
Sos un asistente especializado en la Ley 20.009 sobre fraude bancario
chileno. Tu trabajo es responder preguntas usando EXCLUSIVAMENTE la
información presente en los chunks recuperados.

REGLAS ESTRICTAS:
1. NO inventes información que no esté literalmente en los chunks. Si
   los chunks no responden la pregunta, decilo explícitamente.
2. Citá siempre los artículos e incisos específicos de donde sale cada
   parte de tu respuesta. Si una afirmación viene del Art. 5 inciso 1,
   mencionalo.
3. Si los chunks contienen información parcial o si hay condiciones que
   dependen de otros campos no presentes en la pregunta, ponelos en
   'advertencias'.
4. Si detectás que la pregunta del usuario tiene ambigüedad (puede tener
   múltiples interpretaciones), aclaralo en 'advertencias'.
5. La respuesta debe ser PRECISA. Mejor decir "no puedo responder con
   la información disponible" que inventar.
6. Devolvé SOLO un objeto JSON válido con el schema dado. Sin texto
   antes ni después.
7. En 'articulos_citados' incluí solo los artículos/incisos de donde
   efectivamente sacaste información para tu respuesta, no todos los
   chunks recuperados.
8. Calibración de confianza:
   - 'alta' si la respuesta es directa y los chunks la cubren
     completamente.
   - 'media' si hay que inferir o combinar varios chunks.
   - 'baja' si los chunks son tangenciales o no responden la pregunta
     directamente.

SCHEMA DE RESPUESTA (devolvé exactamente esta estructura):
{
  "respuesta": "texto en lenguaje natural",
  "articulos_citados": [
    {"articulo": 5, "sufijo": null, "inciso": 1, "documento": "Ley 20.009"}
  ],
  "confianza": "alta" | "media" | "baja",
  "razon_confianza": "explicación corta",
  "advertencias": ["..."]
}
"""


def _client() -> OpenAI:
    return OpenAI()


def _formatear_chunks(chunks: list[dict[str, Any]]) -> str:
    out = []
    for i, c in enumerate(chunks, 1):
        m = c["metadata"]
        if m.get("tipo") == "nota":
            etiqueta = f"NOTA → Art {m.get('articulo_relacionado')}"
        else:
            suf = f" {m['articulo_sufijo']}" if m.get("articulo_sufijo") else ""
            etiqueta = f"Art {m.get('articulo')}{suf}, inciso {m.get('inciso')}"
        sim = c.get("similitud", 0.0)
        out.append(
            f"[Chunk {i}] {etiqueta}  (sim={sim:.3f})\n{c['contenido']}\n"
        )
    return "\n".join(out)


def generar_respuesta(query: str, k: int = 10) -> dict[str, Any]:
    """query → cascade retrieval → LLM final → dict JSON estructurado."""
    cascade = buscar_en_cascada(query, k=k)
    chunks = cascade["chunks"]

    user_msg = (
        f"PREGUNTA DEL USUARIO:\n{query}\n\n"
        f"CHUNKS RECUPERADOS (top-{len(chunks)} por similitud):\n"
        f"{_formatear_chunks(chunks)}\n"
        f"DATOS DE RETRIEVAL:\n"
        f"- Estrategia usada: {cascade['estrategia']}\n"
        f"- Top-1 sim: {cascade['sim_top1']:.3f}\n"
        f"- Total chunks: {len(chunks)}\n\n"
        f"Generá la respuesta estructurada en JSON."
    )

    resp = _client().chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURA,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    parsed = json.loads(resp.choices[0].message.content)
    parsed["estrategia_retrieval"] = cascade["estrategia"]
    parsed["chunks_usados"] = len(chunks)
    return parsed
