#!/usr/bin/env python
"""Seed AegisFlow reference data and a demo transaction set."""
from __future__ import annotations
 
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
 
import psycopg
from psycopg.rows import dict_row
 
DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'aegisflow')} user={os.getenv('DB_USER', 'aegis')} "
    f"password={os.getenv('DB_PASS', 'aegis_dev_2026')}"
)
 
RULES = [
    ('R001_HIGH_VALUE', 1, 'Single transaction above reporting threshold', 25,
     '{"threshold_amount": 500000}'),
    ('R002_VELOCITY_1H', 1, 'More than N transactions in a rolling hour', 20,
     '{"max_txn_per_hour": 12}'),
    ('R003_STRUCTURING', 1, 'Multiple sub-threshold debits summing above the report limit', 35,
     '{"window_hours": 24, "report_limit": 1000000}'),
    ('R004_NEW_BENEFICIARY', 1, 'High-value transfer to a beneficiary first seen recently', 15,
     '{"account_age_days": 7}'),
    ('R005_HIGH_RISK_COUNTRY', 1, 'Counterparty in a high-risk jurisdiction', 30, '{}'),
    ('R006_DORMANT_REACTIVATION', 1, 'Activity on an account dormant beyond N days', 20,
     '{"dormancy_days": 180}'),
]
 
WATCHLIST = [
    ('internal', 'Vela Holdings Ltd', 'organisation', 'CY'),
    ('internal', 'Arun Bhaskar', 'individual', 'IN'),
    ('ofac', 'Northbridge Trading FZE', 'organisation', 'AE'),
]
 
HIGH_RISK = ['KP', 'IR', 'SY', 'MM']
 
 
def seed_rules(cur) -> None:
    cur.executemany(
        'INSERT INTO rule_definitions (rule_code, version, description, weight, params) '
        'VALUES (%s, %s, %s, %s, %s::jsonb) ON CONFLICT DO NOTHING',
        RULES,
    )
 
 
def seed_watchlist(cur) -> None:
    cur.executemany(
        'INSERT INTO watchlist_entries (list_name, entity_name, entity_type, country_code) '
        'VALUES (%s, %s, %s, %s)',
        WATCHLIST,
    )
 
 
def seed_customers(cur, n: int = 120) -> list[str]:
    account_ids: list[str] = []
    for i in range(n):
        cur.execute(
            'INSERT INTO customers (external_ref, full_name, date_of_birth, country_code, '
            'kyc_status, risk_rating, is_pep) VALUES (%s, %s, %s, %s, %s, %s, %s) '
            'RETURNING customer_id',
            (f'CUST{i:05d}', f'Demo Customer {i:03d}', '1988-04-17',
             random.choice(['IN', 'IN', 'IN', 'SG', 'AE']),
             'verified', random.choice(['low', 'low', 'medium', 'high']), i % 37 == 0),
        )
        customer_id = cur.fetchone()['customer_id']
        for a in range(random.randint(1, 2)):
            cur.execute(
                'INSERT INTO accounts (customer_id, account_number, account_type, currency, '
                'opened_on, last_active_on, status) VALUES (%s, %s, %s, %s, %s, %s, %s) '
                'RETURNING account_id',
                (customer_id, f'IN66AEGS{i:07d}{a}', random.choice(['current', 'savings', 'card']),
                 'INR', '2021-06-01', '2026-09-01', 'active'),
            )
            account_ids.append(cur.fetchone()['account_id'])
    return account_ids
 
 
def seed_transactions(cur, account_ids: list[str], n: int = 5000) -> None:
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(n):
        account_id = random.choice(account_ids)
        amount = round(random.choice([
            random.uniform(100, 5_000),
            random.uniform(5_000, 90_000),
            random.uniform(400_000, 900_000),
        ]), 2)
        rows.append((
            f'TXN{i:07d}', account_id,
            random.choice(['card', 'wire', 'upi', 'atm']),
            random.choice(['debit', 'debit', 'credit']),
            amount, 'INR', f'{random.randint(4000, 7999)}',
            random.choice(['IN', 'IN', 'IN', 'SG'] + HIGH_RISK[:1]),
            f'dev-{uuid.uuid4().hex[:10]}',
            now - timedelta(minutes=random.randint(0, 60 * 24 * 30)),
        ))
    cur.executemany(
        'INSERT INTO transactions (external_ref, account_id, channel, direction, amount, '
        'currency, merchant_mcc, country_code, device_id, occurred_at) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING',
        rows,
    )
 
 
def main() -> None:
    random.seed(20260911)
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS c FROM customers')
            if cur.fetchone()['c'] > 0:
                print('already seeded — run `make reset` first to reseed')
                return
            seed_rules(cur)
            seed_watchlist(cur)
            account_ids = seed_customers(cur)
            seed_transactions(cur, account_ids)
            cur.execute(
                "INSERT INTO audit_log (actor, action, resource_type, resource_id, detail) "
                "VALUES ('seed_script', 'SEED', 'database', 'aegisflow', '{\"milestone\": \"M1\"}')"
            )
        conn.commit()
    print('seeded: 6 rules, 3 watchlist entries, 120 customers, ~180 accounts, 5000 transactions')
 
 
if __name__ == '__main__':
    main()
