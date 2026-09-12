# ADR-0001: Use Kafka as the inter-agent transport
 
**Status:** Accepted
**Date:** 2026-09-11
 
## Context
 
Agents must be independently scalable and must not lose events during a restart.
A synchronous REST chain couples availability: if the scorer is down, ingestion fails.
 
## Decision
 
All inter-agent communication uses Kafka topics. REST is used only at the edge
(`ingest-gateway` inbound, `case-api` outbound). Topics are keyed by `account_id`
to guarantee per-account ordering, which AML window rules depend on.
 
## Consequences
 
+ Agents restart without data loss; replay is possible for back-testing.
+ Per-account ordering is free.
- Adds Zookeeper and Kafka to the local stack (heavier dev footprint).
- Consumers must be idempotent; alert dedup key is mandatory.