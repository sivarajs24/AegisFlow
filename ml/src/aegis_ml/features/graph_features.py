"""Hourly graph feature job (FR-4). Loads entity_edges into an undirected NetworkX
graph (a ring shares devices regardless of edge direction) and computes, per account:
  component_size  nodes in the account's connected component (accounts+devices+IPs+merchants)
  dist_to_fraud   hop count to the nearest known-fraud account (-1 = unreachable)
  risk_rank       personalised PageRank seeded on known-fraud accounts
Writes gfeat:acct:{id} (TTL 2 h) and one graph_feature_snapshots row per account
(Decision D7), so offline training joins the snapshot that existed at each ts.

python -m aegis_ml.features.graph_features [--once]"""
import argparse
import os
import time
from datetime import datetime, timezone

import networkx as nx
import pandas as pd

from . import definitions as D

PREFIX = {"account": "acct", "device": "dev", "ip": "ip", "merchant": "mer"}
EDGES_SQL = "SELECT src_type, src_id, dst_type, dst_id, weight FROM entity_edges"
FRAUD_SQL = ("SELECT entity_id FROM known_fraud_entities "
             "WHERE entity_type = 'account' AND confirmed_at <= %s")
SNAP_SQL = ("INSERT INTO graph_feature_snapshots "
            "(entity_id, computed_at, component_size, dist_to_fraud, risk_rank) "
            "VALUES (%s, %s, %s, %s, %s)")


def node(entity_type: str, entity_id) -> str:
    return f"{PREFIX[entity_type]}:{entity_id}"


def build_graph(edges) -> nx.Graph:
    g = nx.Graph()
    for src_type, src_id, dst_type, dst_id, weight in edges:
        a, b = node(src_type, src_id), node(dst_type, dst_id)
        w = float(weight or 1.0)
        if g.has_edge(a, b):  # same pair via two edge types
            g[a][b]["weight"] += w
        else:
            g.add_edge(a, b, weight=w)
    return g


def compute(g: nx.Graph, fraud_accounts) -> pd.DataFrame:
    accounts = [n for n in g if n.startswith("acct:")]
    size = {}
    for comp in nx.connected_components(g):
        for n in comp:
            size[n] = len(comp)
    sources = [node("account", a) for a in fraud_accounts if node("account", a) in g]
    dist, rank = {}, {}
    if sources:
        # weight=1 per hop: edge weight means link STRENGTH, not distance
        dist = nx.multi_source_dijkstra_path_length(g, sources, weight=lambda u, v, d: 1)
        rank = nx.pagerank(g, alpha=0.85, personalization={s: 1.0 for s in sources},
                           weight="weight")
    return pd.DataFrame({
        "entity_id": [a.split(":", 1)[1] for a in accounts],
        "component_size": [int(size[a]) for a in accounts],
        "dist_to_fraud": [int(dist[a]) if a in dist else -1 for a in accounts],
        "risk_rank": [float(rank.get(a, 0.0)) for a in accounts],
    })


def publish(conn, r, feats: pd.DataFrame, computed_at: datetime) -> None:
    with conn.cursor() as cur:
        cur.executemany(SNAP_SQL, [(row.entity_id, computed_at, row.component_size,
                                    row.dist_to_fraud, row.risk_rank)
                                   for row in feats.itertuples(index=False)])
    conn.commit()
    p = r.pipeline(transaction=False)
    for row in feats.itertuples(index=False):
        key = f"gfeat:acct:{row.entity_id}"
        p.hset(key, mapping={"component_size": row.component_size,
                             "dist_to_fraud": row.dist_to_fraud,
                             "risk_rank": repr(row.risk_rank),
                             "computed_at": computed_at.isoformat()})
        p.expire(key, D.GRAPH_TTL_S)
    p.execute()


def run_once(conn, r) -> int:
    now = datetime.now(timezone.utc)
    g = build_graph(conn.execute(EDGES_SQL).fetchall())
    fraud = [row[0] for row in conn.execute(FRAUD_SQL, (now,)).fetchall()]
    feats = compute(g, fraud)
    publish(conn, r, feats, now)
    return len(feats)


def main():
    import psycopg
    import redis
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval-s", type=int, default=3600)
    a = ap.parse_args()
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    while True:
        started = time.monotonic()
        try:
            with psycopg.connect(dsn) as conn:
                print(f"graph features for {run_once(conn, r)} accounts", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"graph pass failed: {exc}", flush=True)
        if a.once:
            break
        time.sleep(max(0, a.interval_s - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
