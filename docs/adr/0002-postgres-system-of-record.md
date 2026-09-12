# ADR-0002: PostgreSQL is the system of record, Redis is disposable
**Status:** Accepted
**Date:** 2026-09-11
## Context
Velocity counters need sub-millisecond reads. Alerts and cases need durability,
referential integrity and auditability for regulators.
## Decision
## Consequences
PostgreSQL holds every durable entity. Redis holds only derived counters with TTLs
and can be flushed at any time without data loss — counters are rebuildable by
replaying Kafka.
+ Clear recovery story: Redis loss is a warm-cache problem, not an outage.
+ Simple audit surface — one database to inspect.
- Counter rebuild after a Redis wipe costs a replay window.