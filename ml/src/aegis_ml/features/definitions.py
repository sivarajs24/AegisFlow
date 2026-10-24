"""SINGLE SOURCE OF TRUTH for every AegisFlow feature (FR-3, spec section 11).

The online path (services/ingestion/.../online_features.py, a Lua script) and the
offline path (offline.py, batch over a table) both read the windows, defaults and
output order from here. Parity rules (ADR 0001):
  D1 event time: windows use the transaction's own ts, never server time.
  D2 velocity windows are (ts - w, ts], current transaction INCLUDED; ties are
     ordered by (ts, id) in both paths.
  D4 amount_zscore uses the account profile BEFORE the current amount is added."""
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

WINDOWS = {"1m": 60, "1h": 3_600, "24h": 86_400, "7d": 604_800}  # ordered
DISTINCT_WINDOW_S = 86_400  # distinct devices / IPs per account
SHARE_WINDOW_S = 604_800    # distinct accounts per device / IP
KEY_TTL_S = 8 * 86_400      # every Redis key outlives the longest window
GRAPH_TTL_S = 2 * 3_600     # gfeat:* outlives one missed hourly run


@dataclass(frozen=True)
class Feature:
    name: str
    entity: str  # account | device | ip
    kind: str    # count | sum | distinct | zscore | recency | calendar | graph
    window_s: int | None
    include_current: bool
    default: float
    source: str  # lua | calendar | graph


def _velocity():
    out = []
    for label, w in WINDOWS.items():
        out.append(Feature(f"txn_count_{label}", "account", "count", w, True, 0.0, "lua"))
        out.append(Feature(f"amount_sum_minor_{label}", "account", "sum", w, True, 0.0, "lua"))
    return out


FEATURES: list[Feature] = _velocity() + [
    Feature("distinct_devices_24h", "account", "distinct", DISTINCT_WINDOW_S, True, 0.0, "lua"),
    Feature("distinct_ips_24h", "account", "distinct", DISTINCT_WINDOW_S, True, 0.0, "lua"),
    Feature("device_accounts_7d", "device", "distinct", SHARE_WINDOW_S, True, 0.0, "lua"),
    Feature("ip_accounts_7d", "ip", "distinct", SHARE_WINDOW_S, True, 0.0, "lua"),
    Feature("amount_zscore", "account", "zscore", None, False, 0.0, "lua"),
    Feature("seconds_since_prev", "account", "recency", None, False, -1.0, "lua"),
    Feature("hour_of_day", "account", "calendar", None, True, 0.0, "calendar"),
    Feature("day_of_week", "account", "calendar", None, True, 0.0, "calendar"),
    Feature("graph_component_size", "account", "graph", None, False, 1.0, "graph"),
    Feature("graph_dist_to_fraud", "account", "graph", None, False, -1.0, "graph"),
    Feature("graph_risk_rank", "account", "graph", None, False, 0.0, "graph"),
]

FEATURE_LIST = [f.name for f in FEATURES]
BY_NAME = {f.name: f for f in FEATURES}
LUA_OUTPUTS = [f.name for f in FEATURES if f.source == "lua"]  # order the script returns

GRAPH_FIELDS = {"graph_component_size": "component_size",
                "graph_dist_to_fraud": "dist_to_fraud",
                "graph_risk_rank": "risk_rank"}

FEATURE_SET_VERSION = hashlib.sha256(json.dumps(
    [asdict(f) for f in FEATURES] + [WINDOWS, DISTINCT_WINDOW_S, SHARE_WINDOW_S],
    sort_keys=True).encode()).hexdigest()[:12]


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

def epoch_seconds(ts: datetime) -> float:
    """The ONE conversion from timestamp to window clock, used by both paths."""
    return ((ts - _EPOCH) // timedelta(microseconds=1)) / 1_000_000

def calendar(ts: datetime) -> dict:
    u = ts.astimezone(timezone.utc)
    return {"hour_of_day": float(u.hour), "day_of_week": float(u.weekday())}

def amount_minor(amount) -> int:
    """Decimal or 2-dp float -> integer minor units (paise/cents)."""
    if isinstance(amount, Decimal):
        return int((amount * 100).to_integral_value())
    return int(round(float(amount) * 100))
