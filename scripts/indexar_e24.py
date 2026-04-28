"""Indexa el Registro 1 del E24 con chunks de granularidad mínima.

Genera 4 tipos de chunks: contexto_general, campo_descripcion, codigo,
regla_condicional. Detecta discriminadores automáticamente y enriquece
los `campo_descripcion` con `afecta_a` (campos que dependen de él).
"""

import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.chunking import parsear_e24_registro1
from core.db import get_connection
from core.embeddings import embed_batch

_DOC_NOMBRE = "E24"
_DOC_FECHA = date(2025, 8, 28)


def main() -> None:
    path = Path(__file__).resolve().parent.parent / "docs" / "e24.txt"
    texto = path.read_text(encoding="utf-8")
    print(f"Leyendo {path.name} ({len(texto)} bytes)...\n")

    chunks = parsear_e24_registro1(texto)

    # ---- resumen ----
    tipos = Counter(c["metadata"]["tipo"] for c in chunks)
    campos_descritos = sorted({
        c["metadata"]["campo_numero"]
        for c in chunks
        if c["metadata"]["tipo"] == "campo_descripcion"
    })
    discriminadores = sorted([
        (
            c["metadata"]["campo_numero"],
            c["metadata"]["campo_nombre"],
            c["metadata"]["afecta_a"],
        )
        for c in chunks
        if c["metadata"]["tipo"] == "campo_descripcion"
        and c["metadata"].get("es_discriminador")
    ])

    print(f"Chunks generados: {len(chunks)}")
    for t, n in sorted(tipos.items()):
        print(f"  {t}: {n}")
    print(f"\nCampos descritos: {len(campos_descritos)}")
    print(f"  numeración: {campos_descritos}")
    print(f"\nDiscriminadores detectados: {len(discriminadores)}")
    for num, nombre, afecta_a in discriminadores:
        print(f"  Campo {num} ({nombre}): afecta a {afecta_a}")

    # ---- embeddings ----
    print(f"\nGenerando embeddings ({len(chunks)} chunks)...")
    contenidos = [c["contenido"] for c in chunks]
    embeddings = embed_batch(contenidos)

    # ---- persistencia ----
    hash_ = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documentos (nombre, version_fecha, hash_contenido) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (nombre) DO UPDATE "
            "SET version_fecha = EXCLUDED.version_fecha, "
            "    hash_contenido = EXCLUDED.hash_contenido, "
            "    indexado_at = NOW() "
            "RETURNING id",
            (_DOC_NOMBRE, _DOC_FECHA, hash_),
        )
        doc_id = cur.fetchone()[0]
        cur.execute("DELETE FROM chunks WHERE documento_id = %s", (doc_id,))

        for chunk, emb in zip(chunks, embeddings):
            cur.execute(
                "INSERT INTO chunks (documento_id, contenido, embedding, metadata) "
                "VALUES (%s, %s, %s, %s::jsonb)",
                (doc_id, chunk["contenido"], emb, json.dumps(chunk["metadata"])),
            )

    print(f"\nIndexado completo. documento_id={doc_id}, {len(chunks)} chunks.\n")

    # ---- ejemplos: 1 campo_desc, 2 codigos, 1 regla, 1 contexto_general ----
    print("=" * 78)
    print("EJEMPLOS DE CHUNKS")
    print("=" * 78)

    def _primer(tipo: str, n: int = 1) -> list[dict]:
        return [c for c in chunks if c["metadata"]["tipo"] == tipo][:n]

    seleccion = (
        _primer("campo_descripcion", 1)
        + _primer("codigo", 2)
        + _primer("regla_condicional", 1)
        + _primer("contexto_general", 1)
    )
    for i, c in enumerate(seleccion, 1):
        print(f"\n--- Ejemplo {i} ---")
        print(f"metadata: {json.dumps(c['metadata'], ensure_ascii=False)}")
        prev = c["contenido"]
        if len(prev) > 600:
            prev = prev[:600] + "..."
        print(f"contenido:\n{prev}")


if __name__ == "__main__":
    main()
