# AegisFlow — Architecture
 
## 1. Context
 
AegisFlow processes two event classes: card authorisations (high volume, low latency)
and wire transfers (low volume, high value). Both land on the same bus so that AML
typologies can be evaluated across channels. M1 provisions the bus, the store and the
schema; no model is trained yet.
 
## 2. Component Responsibilities
 - **ingest-gateway** — Accepts transaction events over REST, validates the schema, publishes to txn.raw- **transaction-scorer** — Consumes txn.raw, computes velocity features, applies the rule engine and ML
  score, publishes to txn.scored- **alert-orchestrator** — Consumes txn.scored above threshold, deduplicates, opens or updates a case,
  publishes txn.alerted- **case-api** — FastAPI service exposing alerts, cases and investigator actions
 
## 3. Data Flow
 
1. `ingest-gateway` validates the payload against a Pydantic schema and publishes to
   `txn.raw` keyed by `account_id` so all events for an account land on one partition.
2. `transaction-scorer` maintains Redis velocity counters (1m / 1h / 24h windows),
   evaluates the deterministic rule set, and attaches a risk band.
3. `alert-orchestrator` deduplicates by `(account_id, rule_code, window)`, writes the
   alert and opens or appends to a case in PostgreSQL.
4. `case-api` serves alerts and cases; every state change writes to `audit_log`.
 
## 4. Non-Functional Targets
 - p95 scoring latency < 200 ms end to end (measured from M3)
 - Zero transaction loss: Kafka acks=all, consumer commits after DB write
 - Every alert traceable to the exact rule version that fired
 - All investigator actions immutable-logged for regulatory review