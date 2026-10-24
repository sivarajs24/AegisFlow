"""Seed known_fraud_entities from labels dated BEFORE cutoff T0 only (Decision D5).
Simulates "previously confirmed" fraud; graph features may use it, evaluation may not
overlap it. M3 must start its train split at or after T0.

LABEL_SQL assumes M1's ground_truth_labels has (transaction_id, is_fraud). If M1 named
the columns differently, edit LABEL_SQL only.

Usage: DATABASE_URL=... [KNOWN_FRAUD_CUTOFF=2026-09-08T00:00:00Z] python db/seed/seed_known_fraud.py"""
import os
import sys
from datetime import datetime

import psycopg

LABEL_SQL = """
SELECT DISTINCT t.account_id, min(t.ts) OVER (PARTITION BY t.account_id) AS confirmed_at
FROM ground_truth_labels g JOIN transactions t ON t.id = g.transaction_id
WHERE g.is_fraud AND t.ts < %s"""

DEFAULT_CUTOFF_SQL = """
SELECT percentile_disc(0.10) WITHIN GROUP (ORDER BY ts) FROM transactions"""


def main() -> int:
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn:
        env_cut = os.getenv("KNOWN_FRAUD_CUTOFF")
        cutoff = (datetime.fromisoformat(env_cut.replace("Z", "+00:00")) if env_cut
                  else conn.execute(DEFAULT_CUTOFF_SQL).fetchone()[0])
        if cutoff is None:
            print("no transactions yet - run the generator first", file=sys.stderr)
            return 2
        rows = conn.execute(LABEL_SQL, (cutoff,)).fetchall()
        conn.execute("DELETE FROM known_fraud_entities WHERE source = 'seed_pre_T0'")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO known_fraud_entities (entity_type, entity_id, confirmed_at, source) "
                "VALUES ('account', %s, %s, 'seed_pre_T0') ON CONFLICT DO NOTHING", rows)
        conn.commit()
        print(f"T0 = {cutoff.isoformat()} -> {len(rows)} known-fraud accounts seeded")
        print("Record T0 in params.yaml (features.known_fraud_cutoff); M3's train split starts here.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
