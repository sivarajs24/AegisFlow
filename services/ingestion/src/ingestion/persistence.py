"""Transaction insert + entity-edge upserts in ONE database transaction. The edge upsert
only runs when the transaction row was actually inserted, so a retried POST never
inflates edge weights. Requires the unique index from migration m2_0001 (Decision D6)."""
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .schemas import TransactionIn

INSERT_TXN = text("""
INSERT INTO transactions (id, ts, account_id, counterparty_id, merchant_id, device_id, ip_id,
amount, currency, channel)
VALUES (:id, :ts, :account_id, :counterparty_id, :merchant_id, :device_id, :ip_id,
:amount, :currency, :channel)
ON CONFLICT (id) DO NOTHING
RETURNING id""")

UPSERT_EDGE = text("""
INSERT INTO entity_edges (src_type, src_id, dst_type, dst_id, edge_type, first_seen, weight)
VALUES (:src_type, :src_id, :dst_type, :dst_id, :edge_type, :ts, 1)
ON CONFLICT (src_type, src_id, dst_type, dst_id, edge_type)
DO UPDATE SET weight = entity_edges.weight + 1""")


class UnknownEntity(ValueError):
    """A referenced account/device/ip/merchant id does not exist (FK violation)."""


def edges_for(t: TransactionIn) -> list[dict]:
    out = []
    for kind, value, edge in (("device", t.device_id, "uses_device"),
                              ("ip", t.ip_id, "uses_ip"),
                              ("merchant", t.merchant_id, "pays_merchant")):
        if value:
            out.append({"src_type": "account", "src_id": t.account_id, "dst_type": kind,
                        "dst_id": value, "edge_type": edge, "ts": t.ts})
    if t.channel == "transfer" and t.counterparty_id:
        out.append({"src_type": "account", "src_id": t.account_id, "dst_type": "account",
                    "dst_id": t.counterparty_id, "edge_type": "transfers_to", "ts": t.ts})
    return out


class PgStore:
    def __init__(self, engine):
        self.engine = engine

    def store(self, t: TransactionIn) -> bool:
        """True if inserted now, False if the id already existed."""
        try:
            with self.engine.begin() as conn:
                inserted = conn.execute(INSERT_TXN, t.model_dump()).first() is not None
                if inserted:
                    for e in edges_for(t):
                        conn.execute(UPSERT_EDGE, e)
                return inserted
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23503":  # foreign_key_violation
                raise UnknownEntity(str(exc.orig).splitlines()[0]) from None
            raise

    def ping(self) -> bool:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True


class MemoryStore:
    """Test double with the same interface."""
    def __init__(self, known_accounts=None):
        self.rows, self.edges, self.known = {}, {}, known_accounts

    def store(self, t: TransactionIn) -> bool:
        if self.known is not None and str(t.account_id) not in self.known:
            raise UnknownEntity("account not found")
        if str(t.id) in self.rows:
            return False
        self.rows[str(t.id)] = t
        for e in edges_for(t):
            k = (e["src_type"], str(e["src_id"]), e["dst_type"], str(e["dst_id"]), e["edge_type"])
            self.edges[k] = self.edges.get(k, 0) + 1
        return True

    def ping(self) -> bool:
        return True
