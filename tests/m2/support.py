"""Shared builders. stream() makes a deterministic synthetic transaction stream with
ties, shared devices/IPs, missing devices and gaps that cross every window edge -
self-contained so the parity proof does not depend on the M1 generator's internals."""
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
NS = uuid.UUID("0b6c6f2e-2d8a-4f53-9a51-3c1d2b7e8f90")


def stream(n=5000, accounts=300, devices=150, ips=100, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    acc = [str(uuid.uuid5(NS, f"acct-{i}")) for i in range(accounts)]
    dev = [str(uuid.uuid5(NS, f"dev-{i}")) for i in range(devices)]
    ipl = [str(uuid.uuid5(NS, f"ip-{i}")) for i in range(ips)]
    gaps = rng.choice([0, 0, 1, 5, 30, 59, 60, 61, 600, 3600, 86_400], size=n)
    jitter = rng.integers(0, 1_000_000, size=n) / 1e6 * (rng.random(n) < 0.3)
    secs = np.cumsum(gaps) + jitter  # 70% of rows sit on whole seconds
    rows = []
    for i in range(n):
        rows.append({
            "id": str(uuid.uuid5(NS, f"txn-{seed}-{i}")),
            "ts": T0 + timedelta(microseconds=int(round(secs[i] * 1e6))),
            "account_id": acc[int(rng.zipf(1.6)) % accounts],
            "amount_minor": int(rng.integers(100, 500_000)),
            "device_id": None if rng.random() < 0.15 else dev[int(rng.integers(devices))],
            "ip_id": None if rng.random() < 0.10 else ipl[int(rng.integers(ips))],
        })
    return pd.DataFrame(rows)
