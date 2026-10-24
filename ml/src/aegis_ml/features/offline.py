"""Offline, point-in-time feature builder (FR-3). Same definitions, same rules as the
Lua path, written as explicit two-pointer loops so every boundary is visible:
a row only ever sees transactions at or before itself in (ts, id) order.

python -m aegis_ml.features.offline --out data/features/features_pit.parquet"""
import argparse
import math
import os
import pathlib
from collections import Counter

import numpy as np
import pandas as pd

from . import definitions as D

COLUMNS = ["id", "ts", "account_id", "amount_minor", "device_id", "ip_id"]


def prepare(txns: pd.DataFrame) -> pd.DataFrame:
    """Normalise to COLUMNS and sort by (ts, id) - the arrival order the online path sees."""
    f = txns.copy()
    if "amount_minor" not in f:
        f["amount_minor"] = [D.amount_minor(a) for a in f["amount"]]
    for c in ("id", "account_id", "device_id", "ip_id"):
        f[c] = f[c].map(lambda v: None if v is None or (isinstance(v, float) and math.isnan(v))
                        else str(v))
    f["ts"] = pd.to_datetime(f["ts"], utc=True)
    f["t"] = [D.epoch_seconds(x.to_pydatetime()) for x in f["ts"]]
    return f.sort_values(["t", "id"], kind="mergesort").reset_index(drop=True)


def _windowed_counts(times, amounts, w):
    """count and sum over (t_i - w, t_i] for rows of ONE account, in order."""
    n = len(times)
    cnt, sm = np.zeros(n), np.zeros(n)
    prefix = np.concatenate([[0], np.cumsum(amounts)])
    left = 0
    for i in range(n):
        cut = times[i] - w
        while times[left] <= cut:
            left += 1
        cnt[i] = i - left + 1
        sm[i] = prefix[i + 1] - prefix[left]
    return cnt, sm


def _windowed_distinct(times, keys, w):
    """distinct non-null keys over (t_i - w, t_i], rows in order."""
    n = len(times)
    out = np.zeros(n)
    live, left = Counter(), 0
    for i in range(n):
        cut = times[i] - w
        while times[left] <= cut:
            if keys[left] is not None:
                live[keys[left]] -= 1
                if live[keys[left]] == 0:
                    del live[keys[left]]
            left += 1
        if keys[i] is not None:
            live[keys[i]] += 1
        out[i] = len(live)
    return out


def _profile(amounts_minor, times):
    """amount_zscore (profile BEFORE the row) and seconds_since_prev, Welford order
    identical to the Lua script."""
    z, since = np.zeros(len(times)), np.full(len(times), -1.0)
    n, mean, m2, last = 0, 0.0, 0.0, None
    for i, (a, t) in enumerate(zip(amounts_minor, times)):
        x = a / 100
        if n >= 2:
            sd = math.sqrt(m2 / (n - 1))
            if sd > 0:
                z[i] = (x - mean) / sd
        if last is not None:
            since[i] = t - last
        n += 1
        delta = x - mean
        mean = mean + delta / n
        m2 = m2 + delta * (x - mean)
        last = t
    return z, since


def build(txns: pd.DataFrame, snapshots: pd.DataFrame | None = None) -> pd.DataFrame:
    f = prepare(txns)
    out = pd.DataFrame({"id": f["id"], "ts": f["ts"], "account_id": f["account_id"]})
    for name in D.FEATURE_LIST:
        out[name] = float(D.BY_NAME[name].default)
    for _, g in f.groupby("account_id", sort=False):
        idx = g.index.to_numpy()
        t, amt = g["t"].to_numpy(), g["amount_minor"].to_numpy(dtype=np.int64)
        for label, w in D.WINDOWS.items():
            c, s = _windowed_counts(t, amt, w)
            out.loc[idx, f"txn_count_{label}"] = c
            out.loc[idx, f"amount_sum_minor_{label}"] = s
        out.loc[idx, "distinct_devices_24h"] = _windowed_distinct(
            t, g["device_id"].tolist(), D.DISTINCT_WINDOW_S)
        out.loc[idx, "distinct_ips_24h"] = _windowed_distinct(
            t, g["ip_id"].tolist(), D.DISTINCT_WINDOW_S)
        z, since = _profile(amt, t)
        out.loc[idx, "amount_zscore"] = z
        out.loc[idx, "seconds_since_prev"] = since
    for col, feat in (("device_id", "device_accounts_7d"), ("ip_id", "ip_accounts_7d")):
        for _, g in f[f[col].notna()].groupby(col, sort=False):
            out.loc[g.index, feat] = _windowed_distinct(
                g["t"].to_numpy(), g["account_id"].tolist(), D.SHARE_WINDOW_S)
    cal = pd.DataFrame([D.calendar(x.to_pydatetime()) for x in f["ts"]], index=f.index)
    out[["hour_of_day", "day_of_week"]] = cal[["hour_of_day", "day_of_week"]]
    if snapshots is not None and len(snapshots):
        out = attach_graph(out, snapshots)
    out.attrs["feature_set_version"] = D.FEATURE_SET_VERSION
    return out[["id", "ts", "account_id"] + D.FEATURE_LIST]


def attach_graph(feat: pd.DataFrame, snapshots: pd.DataFrame) -> pd.DataFrame:
    """Latest graph snapshot with computed_at <= ts per account (Decision D7)."""
    s = snapshots.rename(columns={"entity_id": "account_id"}).copy()
    s["account_id"] = s["account_id"].astype(str)
    s["computed_at"] = pd.to_datetime(s["computed_at"], utc=True)
    s = s.sort_values("computed_at")
    left = feat.drop(columns=list(D.GRAPH_FIELDS)).reset_index().sort_values("ts")
    merged = pd.merge_asof(left, s, left_on="ts", right_on="computed_at",
                            by="account_id", direction="backward")
    for name, col in D.GRAPH_FIELDS.items():
        merged[name] = merged[col].astype(float).fillna(D.BY_NAME[name].default)
    return merged.sort_values("index").set_index("index").rename_axis(None)[feat.columns]


def main():
    import sqlalchemy as sa
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    eng = sa.create_engine(os.environ["DATABASE_URL"])
    txns = pd.read_sql("SELECT id, ts, account_id, amount, device_id, ip_id FROM transactions",
                       eng)
    snaps = pd.read_sql("SELECT entity_id, computed_at, component_size, dist_to_fraud, "
                        "risk_rank FROM graph_feature_snapshots", eng)
    out = build(txns, snaps)
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(a.out, index=False)
    print(f"{len(out)} rows x {len(D.FEATURE_LIST)} features "
          f"(feature set {D.FEATURE_SET_VERSION}) -> {a.out}")


if __name__ == "__main__":
    main()
