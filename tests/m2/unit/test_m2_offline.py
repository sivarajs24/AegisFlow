"""Hand-computed fixture: window edges, ties, include-current and the z-score order."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from aegis_ml.features import definitions as D
from aegis_ml.features.offline import attach_graph, build

T = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
A, B, DEV = "a", "b", "d1"


def txn(i, sec, acct, minor, dev=DEV):
    return {"id": f"t{i}", "ts": T + timedelta(seconds=sec), "account_id": acct,
            "amount_minor": minor, "device_id": dev, "ip_id": None}


def frame():
    return pd.DataFrame([txn(1, 0, A, 1000), txn(2, 30, A, 2000), txn(3, 30, A, 3000),
                         txn(4, 60, A, 4000), txn(5, 61, B, 500), txn(6, 120, A, 1000, None)])


def test_velocity_edges_and_ties():
    f = build(frame()).set_index("id")
    assert f.loc["t3", "txn_count_1m"] == 3  # t1, t2 and itself (tie with t2)
    assert f.loc["t2", "txn_count_1m"] == 2  # t3 comes AFTER t2 in (ts, id) order
    assert f.loc["t4", "txn_count_1m"] == 3  # t1 sits exactly on the edge: excluded
    assert f.loc["t4", "amount_sum_minor_1m"] == 9000
    assert f.loc["t6", "txn_count_1m"] == 1  # 120 - 60 = 60 > t4: only itself


def test_sharing_and_distinct():
    f = build(frame()).set_index("id")
    assert f.loc["t5", "device_accounts_7d"] == 2  # a and b on d1
    assert f.loc["t6", "device_accounts_7d"] == 0  # no device
    assert f.loc["t6", "distinct_devices_24h"] == 1  # d1 still inside 24h


def test_zscore_uses_profile_before_current():
    f = build(frame()).set_index("id")
    assert f.loc["t1", "amount_zscore"] == 0.0 and f.loc["t2", "amount_zscore"] == 0.0
    mean, sd = 15.0, (50.0) ** 0.5  # profile after t1, t2 = 10, 20
    assert f.loc["t3", "amount_zscore"] == pytest.approx((30 - mean) / sd)
    assert f.loc["t1", "seconds_since_prev"] == -1.0
    assert f.loc["t4", "seconds_since_prev"] == 30.0


def test_graph_join_is_point_in_time():
    snaps = pd.DataFrame([
        {"entity_id": A, "computed_at": T + timedelta(seconds=45), "component_size": 4,
         "dist_to_fraud": 2, "risk_rank": 0.1}])
    f = attach_graph(build(frame()), snaps).set_index("id")
    assert f.loc["t2", "graph_component_size"] == 1.0  # before the snapshot: default
    assert f.loc["t4", "graph_component_size"] == 4.0  # after it: snapshot value
    assert f.loc["t5", "graph_dist_to_fraud"] == -1.0  # account b: no snapshot
    assert list(f.columns[2:]) == D.FEATURE_LIST
