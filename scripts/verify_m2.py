"""M2 definition-of-done checks. Exit 0 means ready to tag v0.2.0-M2.
Needs the stack up (make up-m2), migrations applied, DATABASE_URL/REDIS_URL exported."""
import os
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = [
    "ml/src/aegis_ml/features/definitions.py", "ml/src/aegis_ml/features/offline.py",
    "ml/src/aegis_ml/features/graph_features.py",
    "services/ingestion/src/ingestion/config.py", "services/ingestion/src/ingestion/schemas.py",
    "services/ingestion/src/ingestion/persistence.py",
    "services/ingestion/src/ingestion/online_features.py",
    "services/ingestion/src/ingestion/deps.py", "services/ingestion/src/ingestion/main.py",
    "services/ingestion/src/ingestion/api/routes.py", "services/ingestion/Dockerfile",
    "services/ingestion/requirements.txt", "ml/Dockerfile.graph", "ml/requirements-graph.txt",
    "db/migrations/versions/m2_0001_feature_store.py", "db/seed/seed_known_fraud.py",
    "docker-compose.m2.yml", "docs/adr/0001-feature-store.md",
    "tests/m2/unit/test_m2_parity.py", "tests/m2/unit/test_m2_offline.py",
    "tests/m2/unit/test_m2_graph.py", "tests/m2/api/test_m2_api.py", "tests/m2/integration/test_m2_db.py",
]
results = []


def ok(name, cond, detail=""):
    results.append(bool(cond))
    print(f"[{'OK ' if cond else 'XX '}] {name} {detail}")


for f in FILES:
    ok(f"file {f}", (ROOT / f).exists())

sep = os.pathsep
env = {**os.environ, "PYTHONPATH": f"services/ingestion/src{sep}ml/src{sep}."}
r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/m2/unit", "tests/m2/api"],
                   cwd=ROOT, env=env)
ok("unit + API tests (incl. exact parity over 5,000 transactions)", r.returncode == 0)

if not os.getenv("DATABASE_URL"):
    ok("DATABASE_URL exported", False, "(see env.m2.example)")
else:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/m2/integration"],
                       cwd=ROOT, env=env)
    ok("integration tests (edges, FK, graph job)", r.returncode == 0)
    import psycopg
    import redis
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as c:
        n_tx = c.execute("SELECT count(*) FROM transactions").fetchone()[0]
        ok("transactions stored", n_tx > 0, f"({n_tx})")
        dup = c.execute("SELECT count(*) FROM (SELECT 1 FROM entity_edges GROUP BY src_type, "
                        "src_id, dst_type, dst_id, edge_type HAVING count(*) > 1) d").fetchone()[0]
        ok("no duplicate edges", dup == 0)
        snap = c.execute("SELECT max(computed_at) > now() - interval '65 minutes' "
                         "FROM graph_feature_snapshots").fetchone()[0]
        ok("graph snapshot within the last hour", bool(snap))
        kf = c.execute("SELECT count(*) FROM known_fraud_entities").fetchone()[0]
        ok("known fraud seeded (pre-T0)", kf > 0, f"({kf})")
    rds = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    ok("feat:acct:* keys present", bool(next(rds.scan_iter("feat:acct:*", count=1000), None)))
    ok("gfeat:acct:* keys present", bool(next(rds.scan_iter("gfeat:acct:*", count=1000), None)))

base = os.getenv("INGEST_URL", "http://localhost:8001")
for path in ("/health", "/ready"):
    try:
        code = urllib.request.urlopen(base + path, timeout=5).status
    except Exception as exc:  # noqa: BLE001
        code = str(exc)[:60]
    ok(f"ingestion {path}", code == 200, f"({code})")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
