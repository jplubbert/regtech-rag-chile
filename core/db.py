"""Conexión a Postgres con pgvector."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def get_connection() -> psycopg.Connection:
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError(
            f"POSTGRES_PASSWORD vacío. Editá {_ENV_PATH} y reintentá."
        )
    conn = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        dbname=os.environ.get("POSTGRES_DB", "postgres"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=password,
    )
    # Si la extensión vector ya está instalada, registramos el adapter.
    # En el primer setup esto falla silenciosamente: setup_db.py ejecuta
    # CREATE EXTENSION antes de cualquier uso del tipo `vector`.
    try:
        from pgvector.psycopg import register_vector

        register_vector(conn)
    except Exception:
        pass
    return conn
