"""Búsqueda vectorial sobre `chunks` con filtro opcional por metadata."""

import json
from typing import Any

from psycopg.rows import dict_row

from core.db import get_connection
from core.embeddings import embed_text
from core.query_expansion import expandir_query


def buscar_similares(
    query: str,
    k: int = 5,
    metadata_filtro: dict[str, Any] | None = None,
    expandir: bool = True,
) -> list[dict[str, Any]]:
    """Devuelve los top-k chunks más similares a la query (cosine).

    `metadata_filtro` aplica `metadata @> %s::jsonb` antes del ranking.
    `expandir=True` reformula la query a vocabulario legal antes de
    embebir (resuelve mismatches de registro coloquial vs ley formal).
    """
    if expandir:
        query_expandida = expandir_query(query)
        print(f"  [expansión] original:  {query!r}")
        print(f"  [expansión] expandida: {query_expandida!r}")
        texto_para_embed = query_expandida
    else:
        texto_para_embed = query

    embedding = embed_text(texto_para_embed)

    if metadata_filtro:
        sql = """
            SELECT  c.chunk_id, c.documento_id, c.contenido, c.metadata,
                    d.nombre AS documento_nombre,
                    1 - (c.embedding <=> %s::vector) AS similitud
            FROM    chunks c
            JOIN    documentos d ON d.id = c.documento_id
            WHERE   c.metadata @> %s::jsonb
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """
        params = (embedding, json.dumps(metadata_filtro), embedding, k)
    else:
        sql = """
            SELECT  c.chunk_id, c.documento_id, c.contenido, c.metadata,
                    d.nombre AS documento_nombre,
                    1 - (c.embedding <=> %s::vector) AS similitud
            FROM    chunks c
            JOIN    documentos d ON d.id = c.documento_id
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """
        params = (embedding, embedding, k)

    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def buscar_en_cascada(
    query: str,
    k: int = 5,
    umbral: float = 0.6,
    metadata_filtro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retrieval con fallback condicional a query expansion.

    Estrategia:
    1. Buscar con la query original sin expansión.
    2. Si top-1 sim >= `umbral`, confiamos y devolvemos esos chunks.
    3. Si no, reintentamos con la query expandida vía glosario.
    4. Entre ambas, devolvemos la que tenga mejor top-1 sim.

    Devuelve un dict con:
        chunks            list[dict]  resultados ya rankeados
        estrategia        str         'original' | 'expandida_glosario'
                                      | 'original_sin_alternativa_mejor'
        query_usada       str         texto que efectivamente se embebió
        sim_top1          float
        query_original    str         (solo cuando estrategia != 'original')
    """
    chunks_orig = buscar_similares(
        query, k=k, metadata_filtro=metadata_filtro, expandir=False,
    )
    sim_orig = chunks_orig[0]["similitud"] if chunks_orig else 0.0

    if sim_orig >= umbral:
        return {
            "chunks": chunks_orig,
            "estrategia": "original",
            "query_usada": query,
            "sim_top1": sim_orig,
        }

    query_exp = expandir_query(query, modo="glosario")
    chunks_exp = buscar_similares(
        query_exp, k=k, metadata_filtro=metadata_filtro, expandir=False,
    )
    sim_exp = chunks_exp[0]["similitud"] if chunks_exp else 0.0

    if sim_exp > sim_orig:
        return {
            "chunks": chunks_exp,
            "estrategia": "expandida_glosario",
            "query_usada": query_exp,
            "sim_top1": sim_exp,
            "query_original": query,
        }

    return {
        "chunks": chunks_orig,
        "estrategia": "original_sin_alternativa_mejor",
        "query_usada": query,
        "sim_top1": sim_orig,
        "query_original": query,
    }
