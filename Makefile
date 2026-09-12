.PHONY: up down logs ps db-init seed data verify test lint clean reset

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
	docker compose exec -T postgres psql -U $${DB_USER} -d $${DB_NAME} -f /docker-entrypoint-initdb.d/01_init.sql

seed:
	python scripts/seed_db.py

data:
	python scripts/download_datasets.py

verify:
	python scripts/verify_m1.py

test:
	pytest tests/ -v

lint:
	black . && flake8 .

clean:
	find . -name '__pycache__' -type d -exec rm -rf {} +