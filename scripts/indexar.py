"""Indexa un documento: chunking → embeddings → insert."""

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.chunking import chunk_por_caracteres
from core.db import get_connection
from core.embeddings import embed_batch


def indexar_documento(
    path: Path,
    nombre: str | None = None,
    metadata_global: dict | None = None,
) -> int:
    texto = path.read_text(encoding="utf-8")
    if not texto.strip():
        print(f"[skip] Documento vacío: {path}")
        return -1

    nombre = nombre or path.stem
    chunks = chunk_por_caracteres(texto)
    if not chunks:
        print(f"[skip] Sin chunks: {path}")
        return -1

    print(f"Generando embeddings para {len(chunks)} chunks...")
    embeddings = embed_batch(chunks)

    hash_ = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    metadata_global = metadata_global or {}

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documentos (nombre, version_fecha, hash_contenido) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (nombre) DO UPDATE "
            "SET version_fecha = EXCLUDED.version_fecha, "
            "    hash_contenido = EXCLUDED.hash_contenido, "
            "    indexado_at = NOW() "
            "RETURNING id",
            (nombre, date.today(), hash_),
        )
        doc_id = cur.fetchone()[0]

        cur.execute("DELETE FROM chunks WHERE documento_id = %s", (doc_id,))

        for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
            metadata = {**metadata_global, "chunk_idx": idx}
            cur.execute(
                "INSERT INTO chunks (documento_id, contenido, embedding, metadata) "
                "VALUES (%s, %s, %s, %s::jsonb)",
                (doc_id, chunk_text, emb, __import__("json").dumps(metadata)),
            )

    print(f"Documento '{nombre}' (id={doc_id}) indexado: {len(chunks)} chunks.")
    return doc_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="Ruta al documento .txt")
    parser.add_argument("--nombre", default=None, help="Nombre canónico del documento")
    args = parser.parse_args()
    indexar_documento(args.path, args.nombre)


if __name__ == "__main__":
    main()
