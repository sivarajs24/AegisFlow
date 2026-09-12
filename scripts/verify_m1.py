#!/usr/bin/env python
"""M1 acceptance checks for AegisFlow. Exit code 0 means the milestone is done."""
from __future__ import annotations
 
import os
import subprocess
import sys
 
import psycopg
 
DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} port={os.getenv('DB_PORT', '5433')} "
    f"dbname={os.getenv('DB_NAME', 'aegisflow')} user={os.getenv('DB_USER', 'aegis')} "
    f"password={os.getenv('DB_PASS', 'aegis_dev_2026')}"
)
 
EXPECTED_TABLES = {
    'customers', 'accounts', 'counterparties', 'transactions', 'velocity_snapshots',
    'rule_definitions', 'rule_hits', 'risk_assessments', 'alerts', 'cases',
    'case_alerts', 'case_notes', 'watchlist_entries', 'audit_log',
}
 
failures: list[str] = []
 
 
def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)
 
 
def main() -> int:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'")
        found = {r[0] for r in cur.fetchall()}
        missing = EXPECTED_TABLES - found
        check('schema: all 14 tables present', not missing,
              f'missing {sorted(missing)}' if missing else '14/14')
 
        cur.execute('SELECT count(*) FROM rule_definitions')
        n = cur.fetchone()[0]
        check('seed: rule catalogue', n >= 6, f'{n} rules')
        cur.execute('SELECT count(*) FROM transactions')
        n = cur.fetchone()[0]
        check('seed: demo ledger', n >= 1000, f'{n} transactions')
 
        cur.execute('SELECT count(*) FROM watchlist_entries')
        n = cur.fetchone()[0]
        check('seed: watchlist', n >= 3, f'{n} entries')
 
    rc = subprocess.run(['pytest', 'tests/', '-q'], capture_output=True, text=True)
    check('domain: unit tests', rc.returncode == 0, rc.stdout.strip().splitlines()[-1]
          if rc.stdout.strip() else '')
 
    print()
    if failures:
        print(f'M1 NOT COMPLETE — {len(failures)} check(s) failed')
        return 1
    print('M1 COMPLETE — safe to tag v0.1.0-M1')
    return 0
 
 
if __name__ == '__main__':
    sys.exit(main())