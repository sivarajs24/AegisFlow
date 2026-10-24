"""uvicorn ingestion.main:app --host 0.0.0.0 --port 8001"""
import sys

from fastapi import FastAPI
from loguru import logger

from .api import routes

logger.remove()
logger.add(sys.stdout, serialize=True, level="INFO")
app = FastAPI(title="AegisFlow ingestion", version="0.2.0")
app.include_router(routes.router)
