# AegisFlow

**Real-Time Payment Fraud Scoring & Agentic AML Investigation Platform**

AegisFlow pairs a sub-100ms explainable fraud-scoring engine with a multi-agent LLM investigation workbench that turns flagged cases into regulator-style Suspicious Activity Report (SAR) drafts — always reviewed and approved by a human compliance analyst before anything is filed.

Built entirely on public and synthetic data ([IEEE-CIS Fraud Detection](https://www.kaggle.com/c/ieee-fraud-detection) + a bundled AMLSim/SAML-D-style transaction generator), so the full stack runs locally with no proprietary data or paid APIs required.

---

## Why AegisFlow

Fraud and AML operations are broken at both ends:

- **Detection** — legacy rule engines produce 90%+ false positives, block good customers, and are blind to networks: coordinated mule accounts look individually innocent to a per-transaction rule.
- **Investigation** — every flagged case still takes an analyst 2–6 hours to manually pull transaction history, map counterparties, search adverse media, and hand-write a SAR narrative. Backlogs run to weeks.

Most point solutions stop at an unexplained ML score, which is unusable in a compliance setting where every decision must be justified. AegisFlow addresses both halves of the problem: **explainable ML for the millisecond decision**, and **agentic AI for the hours-long investigation**, with a human always in the loop.

## What It Does

1. **Real-time fraud scoring** — every payment is scored in under 100ms using gradient-boosted models (XGBoost champion / LightGBM challenger) fed by an online (Redis) + offline (PostgreSQL) feature store, combining velocity features, behavioral profiles, and graph features (proximity to known-fraud entities). Every score ships with top-5 SHAP reason codes.
2. **Agentic AML investigation** — flagged cases enter a queue where a 6-agent LangGraph team (supervisor, link analyst, pattern analyst, adverse-media researcher, narrative writer, QA reviewer) assembles an evidence pack and drafts a FinCEN-style SAR narrative, with every claim traceable to a source record. Nothing is filed without analyst approval.

## Key Features

- **Sub-100ms scoring pipeline** — pipelined Redis reads, a precomputed TreeSHAP explainer, and a documented degraded mode if the feature store misses.
- **Single-source feature definitions** — one Python module compiles to both the streaming (Redis) and batch (offline/training) feature paths, eliminating training/serving skew.
- **Hybrid decisioning** — ML score + a deterministic, auditable rule layer that can force a decline (sanctions hits, impossible travel) regardless of model score.
- **Champion/challenger MLOps** — challenger model scores in shadow; promotion requires a measured lift and is fully audited via MLflow.
- **Graph-aware fraud detection** — entity graph (accounts ↔ devices ↔ IPs ↔ merchants) with NetworkX-computed connected-component size, shortest-path-to-fraud, and risk propagation.
- **Multi-agent investigation with adversarial QA** — a dedicated QA agent checks every narrative claim against the evidence pack before it can leave draft status; unsupported claims block approval.
- **Zero-autonomy filing policy** — 100% of SAR drafts require human approval, with full version history and audit trail.
- **RBAC + field-level encryption** — JWT auth with role/case-team claims, PII encrypted at rest, pseudonymous entity IDs sent to LLM agents (never raw PII).
- **MCP-exposed investigation tools** — `khop_neighborhood`, `txn_timeline`, `typology_scan`, and adverse-media search are served over the Model Context Protocol under the same RBAC and audit guarantees, for reuse by other vetted agent clients.

## Business Objectives

| # | Objective |
|---|---|
| 1 | p95 end-to-end scoring latency < 100ms (API receipt → decision) |
| 2 | Beat a rules baseline by ≥30% recall at 1% FPR on the IEEE-CIS test split |
| 3 | 100% of decisions carry top-5 SHAP reason codes |
| 4 | Detect ≥80% of injected laundering typologies (smurfing, layering, round-tripping) |
| 5 | Cut simulated investigation time from hours to <15 minutes |
| 6 | 100% of SAR drafts pass through human approval with full audit trail |

## Architecture

```
Transaction Generator ──HTTP──► Ingestion API ──► PostgreSQL (transactions, entities, edges)
(fraud rings +                        │
 AML typologies)                      ├──► Redis (online features: velocity, profiles, graph cache)
                                       ▼
                            Scoring Service (FastAPI)
                            │ rules layer + XGBoost champion + challenger shadow
                            │ SHAP reason codes, calibrated probs
                            ├──► decisions table + audit outbox
                            └──► Alert/Case Engine ──► cases, alerts (PostgreSQL)
                                       │
                                       ▼
                        Investigation Orchestrator (LangGraph multi-agent)
                        │ link analyst · pattern analyst · media researcher (RAG/Qdrant)
                        │ narrative writer · QA reviewer
                                       ▼
                        Case Workbench (React) ◄── Case/SAR API (FastAPI)
                        human review, edit, approve

Offline: feature pipeline ─► training (XGBoost/LightGBM, MLflow) ─► registry ─► champion/challenger
         NetworkX graph job ─► graph features                    ─► drift jobs ─► reports
```

## Tech Stack

| Layer | Technology |
|---|---|
| Scoring / APIs | FastAPI, Python |
| Online feature store | Redis (LUA scripts for atomic windowed updates) |
| Offline store / OLTP | PostgreSQL |
| ML | XGBoost, LightGBM, SHAP, isotonic calibration, MLflow registry |
| Graph features | NetworkX |
| Agent orchestration | LangGraph (supervisor + 5 specialist agents) |
| Retrieval | Qdrant (hybrid dense + sparse search), `bge-small-en-v1.5` embeddings |
| Frontend | React + Vite, TypeScript, d3 / react-force-graph |
| Data versioning | DVC |
| Observability | Prometheus metrics, PSI drift monitoring |
| CI/CD | GitHub Actions (lint/test/build + scheduled retraining) |
| Local orchestration | Docker Compose |

## Getting Started

```bash
git clone https://github.com/<your-org>/aegisflow.git
cd aegisflow
cp .env.example .env

make up         # start postgres, redis, qdrant, mlflow, services, frontend
make seed       # load demo users, rules, sanctions list, adverse-media corpus
make generate   # start streaming synthetic transactions (with injected fraud rings)
```

The full stack — including a live decision feed — is up in about two minutes. Open the React console to watch real-time decisions stream in, then trigger an investigation from the case queue to see the agent team assemble an evidence pack and SAR draft.

Other useful targets:

```bash
make train      # run the offline training pipeline (XGBoost/LightGBM + MLflow)
make test       # unit + integration + API test suites
make loadtest   # Locust run at 300 TPS, asserts p95 < 100ms
```

## Project Structure

```
aegisflow/
├── generator/        # synthetic transaction + laundering-typology generator
├── services/
│   ├── ingestion/     # validation, persistence, atomic online feature updates
│   ├── scoring/       # rules + models + SHAP explanations + decisioning
│   ├── casework/       # case/alert engine, SAR drafting & approval API
│   └── investigator/  # LangGraph multi-agent orchestrator, tools, RAG
├── ml/                # feature definitions, training, evaluation, monitoring
├── frontend/          # React console (live decisions, case workbench, model ops)
├── db/                # Alembic migrations + seed data
├── docs/              # architecture, typologies, ADRs, runbook
└── tests/             # unit, integration, API/RBAC, load, e2e
```

See [`docs/architecture.md`](docs/architecture.md) for the full breakdown and [`docs/typologies.md`](docs/typologies.md) for the laundering patterns the generator injects.

## Agentic Investigation Workflow

A LangGraph supervisor dispatches five specialists (max 12 agent turns), all producing typed, evidence-linked output:

1. **Link Analyst** — maps entity rings via k-hop neighborhood and shared-device queries.
2. **Pattern Analyst** — runs deterministic typology detectors (smurfing/layering/structuring) over transaction timelines.
3. **Adverse-Media Researcher** — hybrid RAG over a bundled news corpus, filtered by case entities.
4. **Narrative Writer** — drafts the SAR in FinCEN style from typed findings only (no raw DB access), citing evidence IDs per paragraph.
5. **QA Reviewer** — adversarially checks every claim against the evidence pack; unsupported claims trigger a revision loop or escalate to the human analyst.

Hallucination mitigation is layered: the writer only sees structured findings (not free-form retrieval), the QA agent independently verifies claims, and the UI blocks approval on any uncited paragraph.

## API Overview

| Endpoint | Method | Auth |
|---|---|---|
| `/api/v1/auth/login` | POST | none |
| `/api/v1/transactions` | POST | service key |
| `/api/v1/score` | POST | service key |
| `/api/v1/thresholds` | GET/PUT | manager |
| `/api/v1/cases` | GET | aml_analyst+ |
| `/api/v1/cases/{id}/investigate` | POST | aml_analyst+ |
| `/api/v1/cases/{id}/graph` | GET | aml_analyst+ |
| `/api/v1/cases/{id}/disposition` | POST | aml_analyst+ |
| `/api/v1/sar/{case_id}/draft` | GET/PUT | aml_analyst+ |
| `/api/v1/sar/{case_id}/approve` | POST | manager |
| `/api/v1/models`, `/api/v1/drift` | GET | ds/admin |
| `/health`, `/metrics` | GET | none |

Full, always-current contracts are served as OpenAPI specs at `/docs` on each service.

## Testing

- **Unit** — feature-parity fixtures (online vs. offline), rules, decision cost logic, typology detectors, SHAP mapping.
- **Integration** — ingestion→Redis atomicity, model registry promote/rollback, graph feature jobs, outbox audit delivery (via testcontainers).
- **API** — full RBAC matrix (every endpoint × role) and PII-masking tests.
- **AI eval** — recall@1%FPR gate in the retrain workflow; agent golden-case suite requiring evidence recall ≥ 0.8 and narrative faithfulness = 1.0.
- **Performance** — Locust at 300 TPS asserting p95 < 100ms; a Redis-miss degraded-mode chaos test.
- **E2E** — inject a smurfing ring → alert → case → investigation → draft → approve → export.

## Security

- JWT auth with role + case-team claims; rotating service keys on the scoring path.
- PII encrypted at rest, masked in API responses by default, and never sent raw to LLM agents (pseudonymous entity IDs only, re-mapped to display names in the UI).
- Append-only audit log via the transactional outbox pattern; SAR drafts are immutable per version.
- Prompt-injection defense: retrieved media is wrapped as untrusted input, and agents can only call a whitelisted set of tools — no free-form querying.

## Roadmap

- Kafka streaming backbone
- GNN-based (GraphSAGE) entity risk model
- Real sanctions/PEP list integration
- Device-fingerprint SDK
- Active learning for label-efficient retraining
- Multi-tenant deployment
- Case-outcome forecasting
- Temporal/Airflow orchestration of retraining

## Milestones

| Milestone | Deliverables |
|---|---|
| M1 | Repo + compose, schema/migrations, synthetic generator with typologies, IEEE-CIS ETL (DVC) |
| M2 | Feature definitions module, offline builder, online Redis path + parity tests, entity graph + graph features |
| M3 | Fraud models + calibration + MLflow, evaluation suite, champion/challenger registry policy |
| M4 | Scoring service (rules, SHAP, decisions, shadow), load tests to SLO, alert/case engine |
| M5 | Investigator agents + tools + golden-case eval, adverse-media RAG, SAR draft/edit/approve flow |
| M6 | React workbench complete, RBAC/audit/PII hardening, drift + retrain workflow, E2E tests, docs + demo |

## License

Add your chosen license here (e.g., MIT, Apache-2.0).

---

*AegisFlow is a portfolio/demo project built on public and synthetic data. It is not a certified compliance product and is not intended for use with real customer financial data.*
