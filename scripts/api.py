"""HTTP API que expone predictor + detector de anomalías para otros sistemas.

Endpoints:
  GET  /health
  POST /predecir-cronograma   body = caso_dict
  POST /detectar-anomalias    body = {"casos": [...], "hoy": "YYYY-MM-DD"}

Levantar:
  uvicorn scripts.api:app --port 8001 --host 127.0.0.1
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException

from core.anomalias import detectar_anomalias
from core.predictor import predecir_cronograma

app = FastAPI(
    title="regtech-rag-chile API",
    description="Predictor de cronogramas E24 + detector de anomalías LSC.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "regtech-rag-chile"}


@app.post("/predecir-cronograma")
def endpoint_predecir(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        raise HTTPException(status_code=400, detail="payload vacío")
    return predecir_cronograma(payload)


@app.post("/detectar-anomalias")
def endpoint_anomalias(payload: dict[str, Any]) -> dict[str, Any]:
    casos = payload.get("casos") or []
    if not isinstance(casos, list):
        raise HTTPException(status_code=400, detail="`casos` debe ser una lista")
    hoy = payload.get("hoy")
    return {"anomalias": detectar_anomalias(casos, hoy=hoy)}
