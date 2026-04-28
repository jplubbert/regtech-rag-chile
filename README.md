# regtech-rag-chile

Compliance reasoning over Chilean banking fraud regulation: RAG on Ley 20.009 + CMF E24, plus a reactive cronogram predictor and an LSC anomaly detector — exposed over HTTP and consumed by [deadline-chaser](https://github.com/jplubbert/deadline-chaser).

## Overview

When a fraud claim under Ley 20.009 reaches a Chilean bank, the compliance officer has to answer two questions that look simple but are not:

1. **What does the law actually require here?** Refunding within 10 business days, splitting payments above 35 UF, suspending the timeline if it goes to court, the rule changes by ATM/non-ATM, by reinforced authentication, by claim status. The text of the law is short; the operational decision tree on top of it is not.
2. **What dates am I committing to and what fields do I have to fill in the regulatory E24 file?** Every claim writes a row into the CMF's E24 form with field-level interdependencies (Field 17 changes how Fields 26 and 28 must look; Field 33 nullifies Field 26).

This project answers both. It indexes Ley 20.009 and the E24 instructions in pgvector with article-level metadata, retrieves grounded answers with a confidence-cascade, and from a structured case dictionary computes the legal cronogram (critical dates, payment splits, applicable scenarios) with citations into the law.

Audience: compliance officers, fraud-prevention analysts, and the AI agents (like deadline-chaser) that coordinate them.

## Architecture

```
                    ┌─────────────────────────────────┐
                    │   deadline-chaser (agent)       │
                    │   LangChain @tool calls         │
                    └────────────┬────────────────────┘
                                 │ HTTP
                                 ▼
                ┌────────────────────────────────────┐
                │   FastAPI  (scripts/api.py)        │
                │   :8001                            │
                │   /predecir-cronograma             │
                │   /detectar-anomalias              │
                │   /health                          │
                └─────┬─────────────────────┬────────┘
                      │                     │
        ┌─────────────▼─────┐     ┌─────────▼──────────┐
        │   Predictor       │     │  Anomaly Detector  │
        │   (predictor.py)  │     │  (anomalias.py)    │
        │                   │     │                    │
        │  - business-day   │     │  5 grouping rules  │
        │    arithmetic     │     │  over LSC cases    │
        │    (holidays-cl)  │     │                    │
        │  - UF resolver    │     └────────────────────┘
        │  - threshold      │
        │    split @ 35 UF  │
        │  - alerts         │
        └─────────┬─────────┘
                  │
        ┌─────────▼──────────┐         ┌──────────────────┐
        │   Retrieval        │         │  UF Cache        │
        │  (retrieval.py)    │         │  (valores_uf)    │
        │                    │         │                  │
        │  cascade:          │         │  DB → API →      │
        │  query → exp(LLM)  │         │  prev-DB →       │
        │  → cosine over     │         │  hardcoded       │
        │  HNSW vector index │         └────────┬─────────┘
        └─────────┬──────────┘                  │
                  │                             │
        ┌─────────▼─────────────────────────────▼────────┐
        │           Postgres + pgvector                  │
        │                                                │
        │   chunks (embedding vector(1536), metadata)    │
        │   documentos                                   │
        │   valores_uf (date PK, value)                  │
        └────────────────────────────────────────────────┘
```

## Key features

- **RAG over Ley 20.009 and CMF E24** with hierarchical metadata (`articulo`, `articulo_sufijo`, `inciso`, `tipo`) — citations land on the right inciso, not on the article header.
- **Cascade retrieval** with confidence threshold (0.6) and a canonical glossary that translates colloquial queries (*"me robaron la tarjeta"*) into the law's vocabulary (*"hurto, robo o extravío del medio de pago"*) only when the raw query underperforms.
- **Reactive cronogram predictor** that walks the E24 decision tree from a structured case and returns critical dates with grounded legal citations, computing business days against Chilean banking holidays via `holidays-cl`.
- **Dynamic UF resolution** with a four-tier cascade: local `valores_uf` table → `mindicador.cl` API (persisted on read) → most recent prior date in DB → hardcoded fallback. No daily fetches; one cache hit per (date, claim).
- **LSC anomaly detector** that scans batches of claims for 5 grouping inconsistencies (cross-RUT groupings, overlapping windows, individual-vs-grouped duplicates, monto mismatches, overdue payments without justification).
- **FastAPI integration layer** consumed by deadline-chaser as a LangChain `@tool`, so the chaser can request the cronogram for a case and turn each critical date into a follow-up email.

## Tech stack

- Python 3.11+
- PostgreSQL 17 + [pgvector](https://github.com/pgvector/pgvector) (HNSW with `vector_cosine_ops`, GIN on JSONB metadata)
- OpenAI `text-embedding-3-small` (1536 dim) + `gpt-4o-mini` for query expansion and structured answers
- FastAPI + Uvicorn for the HTTP layer
- [`holidays-cl`](https://pypi.org/project/holidays/) for Chilean banking-holiday arithmetic
- [`mindicador.cl`](https://mindicador.cl/api) public API for UF values

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/jplubbert/regtech-rag-chile
cd regtech-rag-chile
python -m venv venv
source venv/Scripts/activate          # Windows: venv\Scripts\activate.bat
pip install -r requirements.txt

# 2. Postgres with pgvector (port 5433 to avoid clashes)
docker run -d --name postgres-rag-chile \
  -e POSTGRES_PASSWORD=password \
  -e TZ=America/Santiago \
  -p 5433:5432 \
  pgvector/pgvector:pg17

# 3. Configure .env
cp .env.example .env
# Edit OPENAI_API_KEY

# 4. Schema (vector ext + tables + HNSW + GIN)
python scripts/setup_db.py

# 5. Index source documents
python scripts/indexar_ley.py    # Ley 20.009 → chunks with article/inciso metadata
python scripts/indexar_e24.py    # CMF E24 instructions → chunks with field-level metadata

# 6. Backfill UF values (skip weekends and Chilean holidays automatically)
python scripts/actualizar_uf.py --ultimo-anio

# 7. Serve the API
uvicorn scripts.api:app --port 8001 --host 127.0.0.1
```

## Project structure

```
regtech-rag-chile/
├── core/
│   ├── chunking.py          Article/inciso parser for Ley 20.009
│   ├── embeddings.py        OpenAI text-embedding-3-small wrapper
│   ├── db.py                Postgres connection + vector registration
│   ├── retrieval.py         Cascade search (raw → glossary expansion)
│   ├── query_expansion.py   LLM expansion + canonical glossary
│   ├── respuesta.py         Structured-JSON answers with citations
│   ├── predictor.py         E24 cronogram from case dict
│   └── anomalias.py         LSC grouping anomaly rules
├── scripts/
│   ├── setup_db.py          Schema + HNSW + GIN indexes
│   ├── indexar_ley.py       Indexer for Ley 20.009
│   ├── indexar_e24.py       Indexer for CMF E24 (inter-field rule detection)
│   ├── actualizar_uf.py     UF backfill from mindicador.cl
│   ├── api.py               FastAPI surface
│   ├── consultar.py         Retrieval CLI
│   ├── responder.py         End-to-end Q&A CLI
│   └── test_*.py            Retrieval, cascade, predictor and anomaly checks
├── docs/
│   ├── ley_20009.txt
│   └── e24.txt
├── data/
│   └── golden_set.yaml      Canonical Q&A set for benchmarking
├── requirements.txt
└── README.md
```

## Sample queries

Live retrieval over the indexed Ley 20.009. Top-1 result shown.

**Q: "¿Qué es autenticación reforzada?"** *(definitional)*

```
[1] sim=0.71  Ley 20.009 Art. 4 inc. 10
    "Para los efectos de esta ley, se entenderá por autenticación reforzada
     aquella que utiliza al menos dos de los siguientes factores: algo que
     sólo el usuario conoce, algo que sólo el usuario posee, y algo que el
     usuario es..."
```

**Q: "¿En qué casos puede el banco solicitar suspensión judicial de la restitución?"** *(procedural)*

```
[1] sim=0.68  Ley 20.009 Art. 5 bis inc. 1
    "El emisor podrá solicitar al juez de policía local la suspensión de
     la obligación de restituir cuando existan antecedentes suficientes
     para presumir que el reclamo es injustificado, doloso o existe culpa
     grave del usuario..."
```

**Q: "¿Qué hago si me roban la tarjeta?"** *(colloquial — triggers glossary expansion)*

```
expansion: "obligaciones del usuario en caso de hurto, robo o extravío
            del medio de pago, plazo aviso al emisor"
[1] sim=0.66  Ley 20.009 Art. 2
    "El usuario deberá dar aviso al emisor del medio de pago del hurto,
     robo, extravío o cualquier otro evento que comprometa..."
```

## Sample cronogram

Input (POST `/predecir-cronograma`):

```json
{
  "id_caso": "C-2026-001",
  "rut_usuario": "12.345.678-9",
  "fecha_aviso": "2026-04-14",
  "fecha_reclamo": "2026-04-15",
  "monto_total_impugnado": 2000000,
  "operacion_objeto": "01",
  "estado_denuncia": "01"
}
```

Output (abridged):

```json
{
  "caso": {
    "monto": 2000000,
    "umbral_uf": 35,
    "valor_uf_utilizado": 38553.45,
    "fecha_uf": "2026-04-15",
    "umbral_clp_calculado": 1349371,
    "supera_umbral": true,
    "es_atm_o_avance": false,
    "tipo_pago": "split_dos_pagos"
  },
  "fechas_criticas": [
    {
      "id": "primera_restitucion",
      "evento": "Primera restitución (hasta umbral 35 UF)",
      "monto_aplicable": 1349371,
      "fecha_limite": "2026-04-29",
      "dias_habiles_calculados": 10,
      "feriados_considerados": [],
      "campo_e24": 26,
      "fundamento_legal": {
        "ley_referencia": "Ley 20.009 Art. 5 inc. 1",
        "extracto": "El emisor deberá cancelar los cargos o restituir los fondos...",
        "similitud": 0.74
      }
    },
    {
      "id": "segunda_restitucion",
      "evento": "Segunda restitución (monto sobre umbral)",
      "monto_aplicable": 650629,
      "fecha_limite": "2026-05-11",
      "dias_habiles_calculados": 17,
      "feriados_considerados": ["2026-05-01"],
      "campo_e24": 28
    },
    {
      "id": "plazo_denuncia",
      "evento": "Vencimiento plazo presentación respaldo de denuncia",
      "fecha_limite": "2026-05-29",
      "dias_habiles_calculados": 30,
      "campo_e24": 8
    }
  ],
  "alertas": [
    {
      "tipo": "umbral_excedido",
      "mensaje": "Caso supera umbral de 35 UF ($1,349,371 CLP, valor UF 38553.45): split en 2 pagos requerido."
    }
  ],
  "escenarios_alternativos": [
    {
      "trigger": "Si el emisor solicita suspensión judicial (Campo 17 = 01)",
      "fundamento": "Ley 20.009 Art. 5 bis"
    }
  ]
}
```

The May 1 holiday inside the second-payment window is detected automatically and surfaces in `feriados_considerados`.

## Integration with deadline-chaser

[deadline-chaser](https://github.com/jplubbert/deadline-chaser) is the companion project — an AI agent that chases people for regulatory data corrections. It consumes this API as a LangChain tool:

```python
@tool
def predecir_cronograma_legal(caso_data: dict) -> dict:
    """Consulta el predictor de regtech-rag-chile..."""
    response = httpx.post(
        f"{REGTECH_API_URL}/predecir-cronograma",
        json=caso_data,
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()
```

End-to-end flow:

```
fraud claim arrives → chaser builds case dict → @tool predecir_cronograma_legal
        → regtech API returns critical dates + legal grounding
        → chaser inserts each date as a `trabajo` in its DB
        → chaser sends targeted follow-up emails as deadlines approach
```

## Performance benchmark

Retrieval evaluation over 8 hand-written queries that vary along axes the retriever struggles on (colloquial vocabulary, definitional vs procedural intent, short keyword fragments, conditional cases). Expected target: at least one chunk from the right `articulo`/`inciso` in the top-3.

| Strategy             | top-1 | top-3 | mean sim |
|----------------------|-------|-------|----------|
| No expansion         | 6/8   | 7/8   | 0.61     |
| Generic LLM expansion| 5/8   | 7/8   | 0.59     |
| Cascade + glossary   | **8/8**| **8/8**| 0.65     |

The cascade strategy uses the raw query first and only falls back to glossary expansion when top-1 similarity drops below 0.6, which avoids the regression that pure expansion introduces on already-canonical queries (Q3, Q6).

Reproduce: `python scripts/test_retrieval.py`.

## Future work

- **Hybrid retrieval**: add BM25 alongside dense vectors and rerank by RRF. Keyword precision matters for queries that name a specific article number.
- **UF auto-update via cron**: today the cache is filled lazily on first read or via `actualizar_uf.py --hoy`. A scheduled daily fetch (skipping non-banking days) would make the first-of-month claim reads instant.
- **Real-time anomaly detection**: the detector runs over a static batch. Wiring it as a Postgres trigger or a stream over LSC writes would surface inconsistencies on the day they appear, not at month close.
- **E24 sub-chunking by discriminator**: fields like Field 17 (judicial suspension request) change the meaning of fields 26–34. Sub-chunks anchored to discriminator combinations would let the retriever return the *applicable* version of a field's instructions instead of the generic one.

## License

MIT.

---

José Pedro Lubbert · 3 years at Banco de Chile (Fraud Prevention & Compliance) · [github.com/jplubbert](https://github.com/jplubbert)
