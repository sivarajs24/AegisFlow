"""HTTP contract with in-memory store + fakeredis: created vs duplicate, retry after a
Redis outage completes features exactly once, validation and auth."""
import uuid

import fakeredis
import pytest
import redis as redis_lib
from fastapi.testclient import TestClient

from ingestion import config, deps
from ingestion.main import app
from ingestion.persistence import MemoryStore

KEY = {"X-Service-Key": config.SERVICE_KEY}
ACCT = str(uuid.uuid4())


def body(**over):
    b = {"id": str(uuid.uuid4()), "ts": "2026-09-01T12:00:00Z", "account_id": ACCT,
         "device_id": str(uuid.uuid4()), "amount": "125.50", "currency": "INR",
         "channel": "card"}
    b.update(over)
    return b


@pytest.fixture()
def wired(monkeypatch):
    store, r = MemoryStore(known_accounts={ACCT}), fakeredis.FakeRedis()
    monkeypatch.setattr(deps, "_store", store)
    monkeypatch.setattr(deps, "_redis", r)
    with TestClient(app) as c:
        yield c, store, r


def test_created_then_duplicate(wired):
    c, store, r = wired
    b = body()
    first = c.post("/api/v1/transactions", json=b, headers=KEY)
    assert first.status_code == 201
    assert first.json() == {"id": b["id"], "decision": None, "duplicate": False}
    again = c.post("/api/v1/transactions", json=b, headers=KEY)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert r.zcard(f"vel:acct:{ACCT}:1h") == 1  # counted once
    assert sum(store.edges.values()) == 1  # edge weight not inflated


def test_retry_after_redis_outage_completes_once(wired, monkeypatch):
    c, store, r = wired

    class Down:
        def register_script(self, _):
            def boom(**_):
                raise redis_lib.ConnectionError("down")
            return boom

    b = body()
    monkeypatch.setattr(deps, "_redis", Down())
    assert c.post("/api/v1/transactions", json=b, headers=KEY).status_code == 503
    monkeypatch.setattr(deps, "_redis", r)
    retry = c.post("/api/v1/transactions", json=b, headers=KEY)
    assert retry.status_code == 200 and retry.json()["duplicate"] is True
    assert r.zcard(f"vel:acct:{ACCT}:1h") == 1  # features now present, once


@pytest.mark.parametrize("bad", [{"amount": "10.123"}, {"amount": "-5"},
                                 {"currency": "inr"}, {"channel": "cash"},
                                 {"ts": "2026-09-01T12:00:00"}])
def test_validation(wired, bad):
    c, *_ = wired
    assert c.post("/api/v1/transactions", json=body(**bad), headers=KEY).status_code == 422


def test_unknown_account_is_422(wired):
    c, *_ = wired
    r = c.post("/api/v1/transactions", json=body(account_id=str(uuid.uuid4())), headers=KEY)
    assert r.status_code == 422 and "unknown entity" in r.json()["detail"]


def test_service_key_and_probes(wired):
    c, *_ = wired
    assert c.post("/api/v1/transactions", json=body()).status_code == 401
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/ready").json()["status"] == "ready"
    assert b"af_transactions_total" in c.get("/metrics").content
