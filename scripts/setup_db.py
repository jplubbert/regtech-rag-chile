"""Crea schema + tablas + índices vectoriales para el RAG."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection

_SCHEMA = [
    ("Habilitar extensión vector", "CREATE EXTENSION IF NOT EXISTS vector;"),
    (
        "Setear timezone Chile",
        "ALTER DATABASE postgres SET TIMEZONE TO 'America/Santiago';",
    ),
    (
        "Tabla documentos",
        """
        CREATE TABLE IF NOT EXISTS documentos (
            id              SERIAL PRIMARY KEY,
            nombre          VARCHAR(200) NOT NULL UNIQUE,
            version_fecha   DATE,
            hash_contenido  VARCHAR(64),
            indexado_at     TIMESTAMP DEFAULT NOW()
        );
        """,
    ),
    (
        "Tabla chunks",
        """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id        SERIAL PRIMARY KEY,
            documento_id    INT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
            contenido       TEXT NOT NULL,
            embedding       vector(1536),
            metadata        JSONB DEFAULT '{}'::jsonb
        );
        """,
    ),
    (
        "Índice HNSW vectorial (cosine)",
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops);
        """,
    ),
    (
        "Índice GIN sobre metadata",
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin
        ON chunks USING gin (metadata);
        """,
    ),
    (
        "Tabla valores_uf",
        """
        CREATE TABLE IF NOT EXISTS valores_uf (
            fecha       DATE PRIMARY KEY,
            valor       NUMERIC(10, 2) NOT NULL,
            fuente      TEXT DEFAULT 'mindicador.cl',
            fetched_at  TIMESTAMP DEFAULT NOW()
        );
        """,
    ),
    (
        "Índice valores_uf",
        "CREATE INDEX IF NOT EXISTS valores_uf_fecha_idx ON valores_uf(fecha);",
    ),
]


def main() -> None:
    print("Aplicando schema...\n")
    with get_connection() as conn, conn.cursor() as cur:
        for label, sql in _SCHEMA:
            cur.execute(sql)
            print(f"  ✓ {label}")
    print("\nSchema OK.")


if __name__ == "__main__":
    main()
