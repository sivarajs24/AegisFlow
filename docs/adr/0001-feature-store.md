# ADR 0001 - Feature store parity rules (M2)

Status: accepted (M2)

- D1 Event time: windows use the transaction's ts, passed into Lua; never Redis TIME.
  The generator replays at 10x speed, so wall-clock windows would disagree with offline.
- D2 Velocity windows are (ts - w, ts], current transaction included; ties are ordered by
  (ts, id) in both paths.
- D3 Idempotency: SET seen:txn:{id} NX inside the script; amounts in integer minor units.
- D4 Welford profile in feat:acct:{id}; amount_zscore uses the profile BEFORE the amount.
- D5 Known fraud only from labels dated before cutoff T0 (known_fraud_entities); never
  ground_truth_labels at serve time.
- D6 Unique index on entity_edges (src_type, src_id, dst_type, dst_id, edge_type); edges
  are upserted only when the transaction row is new.
- D7 Hourly graph_feature_snapshots; offline joins the latest snapshot with
  computed_at <= ts.
- D8 Entity upsert endpoints are deferred; the M1 generator keeps seeding entities.
  M1's entity columns are not fixed by the spec, so a generic upsert could violate them.

Floats cross Redis as %.17g strings so they round-trip bit-exactly; the parity test
demands exact equality.
