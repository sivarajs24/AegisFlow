# AegisFlow — Real-Time Fraud & AML Detection Platform
 
AegisFlow is an agentic fraud and anti-money-laundering platform. Transactions enter over a REST
  gateway, flow through a Kafka pipeline, are scored by a hybrid rules + ML engine, and surface as
    investigator-ready cases.
 
## Problem Statement
 
Card and wire fraud must be judged in under 200 ms, but AML typologies (structuring,
layering, rapid movement) only become visible across a window of transactions. A single
synchronous model call cannot do both. AegisFlow splits the problem across cooperating
agents on a shared event bus: fast deterministic rules inline, heavier behavioural
scoring asynchronously, and case management as the system of record.
 
## Architecture (M1 baseline)
 
```
 POST /v1/transactions
        |
        v
 [ingest-gateway] --publish--> (txn.raw) --> [transaction-scorer]
                                                   |  Redis velocity counters
                                                   |  rule engine + ML score
                                                   v
                                              (txn.scored)
                                                   |
                                                   v
                                          [alert-orchestrator]
                                              |          |
                                         PostgreSQL   (txn.alerted)
                                              |
                                              v
                                          [case-api] --> investigator
```
 
## Milestones
 
| Milestone | Focus |
|-----------|-------|
| M1 | Architecture, streaming infrastructure, schema and data foundation |
| M2 | Feature engineering and supervised fraud model training |
| M3 | Real-time scoring service and rule/model blending |
| M4 | Agentic alert triage with an LLM narrative generator |
| M5 | Investigator console and case workflow UI |
| M6 | Deployment, drift monitoring and model governance |

## Quick Start
 
```bash
cp .env.example .env
make up          # start the full infrastructure stack
make db-init     # apply schema (auto-applied on first boot)
make seed        # load reference + demo data
make verify      # M1 acceptance checks
```
 
## Repository Layout
 - `libs/aegis_domain/` — pure Python rules and scoring, no framework imports- `services/` — one container per agent- `scripts/` — schema, topic creation, dataset ETL, seeding, verification- `config/` — topic definitions and risk thresholds- `docs/adr/` — architecture decision records
 
## Tech Stack
 - **Kafka** — Transaction event bus — topics for raw, scored and alerted events- **Zookeeper** — Kafka coordination (single-node dev mode)- **PostgreSQL** — System of record for accounts, alerts, cases and audit- **Redis** — Velocity counters and hot feature cache- **MLflow** — Experiment tracking and model registry from M2 onward- **Kafka UI** — Topic inspection during development
 
## License
 
MIT
