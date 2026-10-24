"""POST /api/v1/transactions: validate -> commit row + edges -> Lua feature update.
The Lua step runs even for a duplicate id: if an earlier attempt committed the row but
died before Redis, the retry completes the features exactly once (seen:txn guard).
Redis down -> 503 so the caller retries; the decision field stays null until M4."""
import secrets

import redis as redis_lib
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .. import config, deps
from ..online_features import update
from ..persistence import UnknownEntity
from ..schemas import TransactionIn, TransactionOut

router = APIRouter()
TXNS = Counter("af_transactions_total", "Transactions received", ["result"])
FEATURE_SECONDS = Histogram("af_online_feature_seconds", "Lua feature update latency")


def require_service_key(x_service_key: str | None = Header(default=None)):
    if x_service_key is None or not secrets.compare_digest(x_service_key, config.SERVICE_KEY):
        raise HTTPException(401, "invalid service key")


@router.post("/api/v1/transactions", response_model=TransactionOut,
             dependencies=[Depends(require_service_key)])
def post_transaction(t: TransactionIn, response: Response):
    try:
        inserted = deps.store().store(t)
    except UnknownEntity as exc:
        TXNS.labels("unknown_entity").inc()
        raise HTTPException(422, f"unknown entity: {exc}") from None
    try:
        with FEATURE_SECONDS.time():
            update(deps.redis_client(), t.feature_input())
    except redis_lib.RedisError as exc:
        TXNS.labels("features_pending").inc()
        logger.error("online feature update failed for {}: {}", t.id, exc)
        raise HTTPException(503, "stored; online features pending - retry the same request") from None
    TXNS.labels("created" if inserted else "duplicate").inc()
    response.status_code = 201 if inserted else 200
    return TransactionOut(id=t.id, duplicate=not inserted)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    checks = {}
    for name, probe in (("database", lambda: deps.store().ping()),
                        ("redis", lambda: deps.redis_client().ping())):
        try:
            checks[name] = bool(probe())
        except Exception:  # noqa: BLE001
            checks[name] = False
    if not all(checks.values()):
        raise HTTPException(503, detail=checks)
    return {"status": "ready", **checks}


@router.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
