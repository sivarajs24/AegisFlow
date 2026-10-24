"""Wire format for POST /api/v1/transactions. Money is Decimal with at most 2 decimal
places (never float), timestamps must carry a timezone."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TransactionIn(BaseModel):
    id: UUID
    ts: datetime
    account_id: UUID
    counterparty_id: UUID | None = None
    merchant_id: UUID | None = None
    device_id: UUID | None = None
    ip_id: UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    channel: Literal["card", "transfer", "wallet"]

    @field_validator("ts")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("ts must carry a timezone")
        return v

    def feature_input(self) -> dict:
        from aegis_ml.features.definitions import amount_minor
        return {"id": str(self.id), "ts": self.ts, "account_id": str(self.account_id),
                "amount_minor": amount_minor(self.amount),
                "device_id": str(self.device_id) if self.device_id else None,
                "ip_id": str(self.ip_id) if self.ip_id else None}


class TransactionOut(BaseModel):
    id: UUID
    decision: str | None = None  # filled by the scoring service in M4
    duplicate: bool = False
