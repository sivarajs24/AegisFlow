"""Ingestion settings from environment variables (dev-only defaults; real values in .env)."""
import os

DATABASE_URL = os.getenv("DATABASE_URL",
                         "postgresql+psycopg://aegisflow:aegisflow@localhost:5432/aegisflow")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SERVICE_KEY = os.getenv("SERVICE_KEY", "dev-service-key")
