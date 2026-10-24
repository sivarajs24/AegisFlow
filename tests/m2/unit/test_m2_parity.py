"""THE M2 contract: for every transaction, the Lua path and the offline builder produce
IDENTICAL features - every row, every column, exact float equality. Runs on fakeredis
always, and also on a real Redis when PARITY_REDIS_URL is set (Lua 5.1 there vs 5.4 in
fakeredis). PARITY_REDIS_URL must point at a SCRATCH database (e.g. /15): the test
flushes it. Never point it at the live feature store.
If this goes red, fix the online code, never the test."""
import os

import pandas as pd
import pytest

from aegis_ml.features import definitions as D
from aegis_ml.features.offline import build, prepare
from ingestion.online_features import update
from tests.m2.support import stream


def _redis_clients():
    import fakeredis
    clients = [("fakeredis", fakeredis.FakeRedis())]
    if os.getenv("PARITY_REDIS_URL"):
        import redis
        r = redis.Redis.from_url(os.environ["PARITY_REDIS_URL"])
        r.flushdb()
        clients.append(("redis", r))
    return clients


@pytest.mark.parametrize("name, r", _redis_clients())
def test_online_equals_offline_for_every_transaction(name, r):
    txns = stream()
    offline = build(txns).set_index("id")[D.FEATURE_LIST]
    online = {}
    for t in prepare(txns).itertuples(index=False):  # (ts, id) arrival order
        row = update(r, {"id": t.id, "ts": t.ts.to_pydatetime(), "account_id": t.account_id,
                         "amount_minor": int(t.amount_minor), "device_id": t.device_id,
                         "ip_id": t.ip_id})
        online[t.id] = row
    online = pd.DataFrame.from_dict(online, orient="index")[D.FEATURE_LIST]
    pd.testing.assert_frame_equal(offline.loc[online.index].astype(float),
                                  online.astype(float), check_exact=True)
    if name == "redis":
        r.flushdb()


def test_stream_really_exercises_the_edges():
    f = prepare(stream())
    assert f["t"].duplicated().any()  # ties
    assert f["device_id"].isna().any()  # missing devices
    gaps = f["t"].diff()
    assert (gaps == 60).any() and (gaps == 3600).any()  # gaps exactly on window edges
