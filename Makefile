.PHONY: up down logs ps db-init seed data verify test lint clean reset

include .env
export

COMPOSE = docker compose -p aegisflow

up:
	$(COMPOSE) up -d --build
	@echo "stack up — run 'make ps' to check health"

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

db-init:
	$(COMPOSE) exec -T postgres psql -U $(DB_USER) -d $(DB_NAME) -f /docker-entrypoint-initdb.d/01_init.sql
seed: export DB_HOST = localhost
seed:
	python scripts/seed_db.py

data:
	python scripts/download_datasets.py

verify: export DB_HOST = localhost
verify:
	python scripts/verify_m1.py

test:
	pytest tests/ -v

lint:
	black . && flake8 .

clean:
	find . -name '__pycache__' -type d -exec rm -rf {} +

# ---- M2 targets ----
PY ?= python
M2_PATH := PYTHONPATH=services/ingestion/src:ml/src:.
M2_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.m2.yml

up-m2:
	$(M2_COMPOSE) up -d --build ingestion graph-job

migrate:
	$(M2_PATH) alembic upgrade head

seed-fraud:
	$(M2_PATH) $(PY) db/seed/seed_known_fraud.py

ingest:
	$(M2_PATH) uvicorn ingestion.main:app --reload --port 8001

graph-once:
	$(M2_PATH) $(PY) -m aegis_ml.features.graph_features --once

features-pit:
	dvc repro features_pit

parity:
	$(M2_PATH) PARITY_REDIS_URL=redis://localhost:6379/15 pytest -q tests/m2/unit/test_m2_parity.py

test-m2:
	$(M2_PATH) pytest -q tests/m2/unit tests/m2/api

test-m2-int:
	$(M2_PATH) pytest -q tests/m2/integration

verify-m2:
	$(M2_PATH) $(PY) scripts/verify_m2.py

m2: test-m2 test-m2-int verify-m2

.PHONY: up-m2 migrate seed-fraud ingest graph-once features-pit parity test-m2 test-m2-int verify-m2 m2
