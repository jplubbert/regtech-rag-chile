# regtech-rag-chile

RAG sobre normativa bancaria chilena (Ley 20.009 + E24 de la CMF). MVP enfocado
en responder preguntas de compliance officers sobre cómo llenar el archivo
regulatorio E24, con razonamiento sobre campos discriminadores y sus
dependencias.

## Stack

- Python 3.11+
- PostgreSQL 17 + pgvector (Docker)
- OpenAI embeddings (`text-embedding-3-small`, 1536 dim)

## Quickstart

```bash
# 1. venv + dependencias
python -m venv venv
source venv/Scripts/activate          # Windows: venv\Scripts\activate.bat
pip install -r requirements.txt

# 2. Postgres con pgvector (puerto 5433 para no chocar con otros proyectos)
docker run -d --name postgres-rag-chile \
  -e POSTGRES_PASSWORD=password \
  -e TZ=America/Santiago \
  -p 5433:5432 \
  pgvector/pgvector:pg17

# 3. Configurar .env
cp .env.example .env
# Editar OPENAI_API_KEY con tu clave

# 4. Inicializar schema (extension vector + tablas + índices HNSW/GIN)
python scripts/setup_db.py

# 5. Indexar un documento
python scripts/indexar.py docs/ley_20009.txt --nombre "Ley 20.009"

# 6. Consultar
python scripts/consultar.py
```

## Estructura

```
core/
├── chunking.py      # naive por caracteres + por secciones
├── embeddings.py    # OpenAI text-embedding-3-small (1536 dim)
├── retrieval.py     # cosine similarity + filtro JSONB sobre metadata
└── db.py            # conexión Postgres + register_vector lazy

scripts/
├── setup_db.py      # CREATE EXTENSION + tablas + HNSW + GIN
├── indexar.py       # chunking + embed_batch + INSERT
└── consultar.py     # CLI interactiva: top-k chunks por query

docs/                # documentos a indexar (vacíos por ahora)
data/                # golden set de QA + criterios
```

## Schema

```
documentos      id, nombre UNIQUE, version_fecha, hash_contenido, indexado_at
chunks          chunk_id, documento_id FK, contenido, embedding vector(1536),
                metadata JSONB
```

Índices:
- HNSW sobre `embedding` con `vector_cosine_ops` para búsqueda semántica O(log N)
- GIN sobre `metadata` para filtros estructurados (ej: `{"documento": "E24"}`)

## Future work

- Chunker semántico que respete fronteras de artículos/incisos.
- Re-ranker (cross-encoder) sobre el top-k inicial.
- Sub-chunking por discriminadores E24 (campos que cambian la lectura del
  resto del registro) con metadata jerárquica.
- Golden set con criterios automáticos de evaluación (precision@k +
  cobertura de las cláusulas relevantes por pregunta).
