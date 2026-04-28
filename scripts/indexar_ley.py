"""Indexa la Ley 20.009 con chunks por inciso + metadata jerárquica."""

import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.chunking import parsear_ley_20009
from core.db import get_connection
from core.embeddings import embed_batch

_DOC_NOMBRE = "Ley 20.009"
_DOC_FECHA = date(2024, 5, 30)


def main() -> None:
    path = Path(__file__).resolve().parent.parent / "docs" / "ley_20009.txt"
    texto = path.read_text(encoding="utf-8")
    print(f"Leyendo {path.name} ({len(texto)} bytes)...\n")

    chunks = parsear_ley_20009(texto)

    # ---- resumen ----
    tipos = Counter(c["metadata"]["tipo"] for c in chunks)
    articulos: dict[tuple[int, str | None], int] = {}
    for c in chunks:
        m = c["metadata"]
        if m["tipo"] != "inciso" or m.get("articulo") is None:
            continue
        key = (m["articulo"], m.get("articulo_sufijo"))
        articulos[key] = articulos.get(key, 0) + 1

    print(f"Chunks generados: {len(chunks)}")
    for tipo, n in tipos.items():
        print(f"  {tipo}: {n}")
    print(f"\nArtículos detectados: {len(articulos)}")
    for (num, suf), n_incisos in sorted(
        articulos.items(), key=lambda x: (x[0][0], x[0][1] or "")
    ):
        etiqueta = f"Artículo {num}" + (f" {suf}" if suf else "")
        print(f"  {etiqueta}: {n_incisos} incisos")

    # ---- embeddings ----
    print(f"\nGenerando embeddings ({len(chunks)} chunks, batches de 96)...")
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

    # ---- ejemplos ----
    print("=" * 78)
    print("EJEMPLOS")
    print("=" * 78)
    ejemplos: list[dict] = []
    # Buscar 3 chunks variados: primer inciso de Art 1, una nota, y un chunk con sub-puntos a)-h)
    for c in chunks:
        m = c["metadata"]
        if not ejemplos:
            if m["tipo"] == "inciso" and m["articulo"] == 1 and m["inciso"] == 1:
                ejemplos.append(c)
        elif len(ejemplos) == 1:
            if m["tipo"] == "nota":
                ejemplos.append(c)
        elif len(ejemplos) == 2:
            if "a)" in c["contenido"] and "b)" in c["contenido"]:
                ejemplos.append(c)
        if len(ejemplos) == 3:
            break

    for i, c in enumerate(ejemplos, 1):
        print(f"\n--- Ejemplo {i} ---")
        print(f"metadata: {json.dumps(c['metadata'], ensure_ascii=False)}")
        contenido = c["contenido"]
        preview = contenido if len(contenido) <= 500 else contenido[:500] + "..."
        print(f"contenido:\n{preview}")


if __name__ == "__main__":
    main()
