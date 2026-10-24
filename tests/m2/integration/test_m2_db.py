"""Against the real database (make migrate done). Skipped without DATABASE_URL.
Creates its own accounts/devices and removes everything it wrote."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs the stack")

import psycopg  # noqa: E402
import redis  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from aegis_ml.features import graph_features as G  # noqa: E402
from ingestion.persistence import PgStore, UnknownEntity  # noqa: E402
from ingestion.schemas import TransactionIn  # noqa: E402


@pytest.fixture()
def conn():
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as c:
        yield c


@pytest.fixture()
def ring(conn):
    """Accounts A, B, C on one device; A is known fraud. Cleaned up afterwards."""
    accts = [uuid.uuid4() for _ in range(3)]
    dev = uuid.uuid4()
    for a in accts:
        conn.execute("INSERT INTO accounts (id) VALUES (%s)", (a,))
        conn.execute("INSERT INTO devices (id) VALUES (%s) ON CONFLICT DO NOTHING", (dev,))
        conn.execute("INSERT INTO known_fraud_entities VALUES ('account', %s, now() - interval '1 day', 'it_test') ON CONFLICT DO NOTHING", (accts[0],))
    conn.commit()
    yield accts, dev
    ids = [str(a) for a in accts]
    conn.execute("DELETE FROM graph_feature_snapshots WHERE entity_id = ANY(%s::uuid[])", (ids,))
    conn.execute("DELETE FROM entity_edges WHERE src_id = ANY(%s::uuid[])", (ids,))
    conn.execute("DELETE FROM transactions WHERE account_id = ANY(%s::uuid[])", (ids,))
    conn.execute("DELETE FROM known_fraud_entities WHERE source = 'it_test'")
    conn.execute("DELETE FROM accounts WHERE id = ANY(%s::uuid[])", (ids,))
    conn.execute("DELETE FROM devices WHERE id = %s", (dev,))
    conn.commit()


def txn(account, device, minute):
    return TransactionIn(id=uuid.uuid4(), account_id=account, device_id=device,
                         ts=datetime(2026, 9, 1, 12, minute, tzinfo=timezone.utc),
                         amount=Decimal("10.00"), currency="INR", channel="card")


def test_store_is_idempotent_and_upserts_edges(conn, ring):
    (a, b, c), dev = ring
    store = PgStore(create_engine(os.environ["DATABASE_URL"]))
    t1 = txn(a, dev, 0)
    assert store.store(t1) is True and store.store(t1) is False
    assert store.store(txn(a, dev, 1)) is True
    w = conn.execute("SELECT weight FROM entity_edges WHERE src_id = %s AND dst_id = %s",
                     (a, dev)).fetchone()[0]
    assert w == 2  # two distinct transactions, retry not counted
    with pytest.raises(UnknownEntity):
        store.store(txn(uuid.uuid4(), dev, 2))


def test_graph_job_publishes_snapshots_and_redis(conn, ring):
    (a, b, c), dev = ring
    store = PgStore(create_engine(os.environ["DATABASE_URL"]))
    for i, acct in enumerate((a, b, c)):
        store.store(txn(acct, dev, 10 + i))
    r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    G.run_once(conn, r)
    row = conn.execute("SELECT component_size, dist_to_fraud FROM graph_feature_snapshots "
                       "WHERE entity_id = %s ORDER BY computed_at DESC LIMIT 1", (b,)).fetchone()
    assert row[0] >= 4 and row[1] == 2
    assert r.hget(f"gfeat:acct:{b}", "dist_to_fraud") == b"2"
    assert 0 < r.ttl(f"gfeat:acct:{b}") <= 7200
    r.delete(*[f"gfeat:acct:{x}" for x in (a, b, c)])


def test_unique_edge_index_exists(conn):
    assert conn.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_entity_edges_key'"
                       ).fetchone() is not None
