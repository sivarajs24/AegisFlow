"""Pure rule engine — no database, no Kafka, no framework imports.
 
Everything here is a deterministic function of the inputs, which is what makes
the rule set unit-testable and replayable.
"""
from __future__ import annotations
 
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
 
HIGH_RISK_COUNTRIES = frozenset({'KP', 'IR', 'SY', 'MM', 'AF'})
 
 
@dataclass(frozen=True)
class Transaction:
    external_ref: str
    account_id: str
    amount: Decimal
    currency: str
    channel: str
    direction: str
    country_code: str
    occurred_at: datetime
    beneficiary_first_seen_at: datetime | None = None
    account_last_active_on: datetime | None = None
 
 
@dataclass(frozen=True)
class Velocity:
    txn_count_1h: int = 0
    txn_count_24h: int = 0
    amount_sum_24h: Decimal = Decimal('0')
    sub_threshold_count_24h: int = 0
 
 
@dataclass(frozen=True)
class RuleHit:
    code: str
    version: int
    weight: int
    evidence: dict
@dataclass
class RuleSet:
    high_value_threshold: Decimal = Decimal('500000')
    max_txn_per_hour: int = 12
    structuring_window_hours: int = 24
    structuring_report_limit: Decimal = Decimal('1000000')
    new_beneficiary_days: int = 7
    dormancy_days: int = 180
    weights: dict = field(default_factory=lambda: {
        'R001_HIGH_VALUE': 25,
        'R002_VELOCITY_1H': 20,
        'R003_STRUCTURING': 35,
        'R004_NEW_BENEFICIARY': 15,
        'R005_HIGH_RISK_COUNTRY': 30,
        'R006_DORMANT_REACTIVATION': 20,
    })
 
    def evaluate(self, txn: Transaction, vel: Velocity) -> list[RuleHit]:
        hits: list[RuleHit] = []
 
        if txn.amount >= self.high_value_threshold:
            hits.append(RuleHit('R001_HIGH_VALUE', 1, self.weights['R001_HIGH_VALUE'],
                                {'amount': str(txn.amount),
                                 'threshold': str(self.high_value_threshold)}))
 
        if vel.txn_count_1h > self.max_txn_per_hour:
            hits.append(RuleHit('R002_VELOCITY_1H', 1, self.weights['R002_VELOCITY_1H'],
                                {'count_1h': vel.txn_count_1h,
                                 'limit': self.max_txn_per_hour}))
 
        if (vel.sub_threshold_count_24h >= 3
                and vel.amount_sum_24h >= self.structuring_report_limit):
            hits.append(RuleHit('R003_STRUCTURING', 1, self.weights['R003_STRUCTURING'],
                                {'sub_threshold_count': vel.sub_threshold_count_24h,
                                 'sum_24h': str(vel.amount_sum_24h)}))
 
        if txn.beneficiary_first_seen_at is not None:
            age = txn.occurred_at - txn.beneficiary_first_seen_at
            if age < timedelta(days=self.new_beneficiary_days) and txn.amount >= Decimal('100000'):
                hits.append(RuleHit('R004_NEW_BENEFICIARY', 1,
                                    self.weights['R004_NEW_BENEFICIARY'],
                                    {'beneficiary_age_days': age.days}))
 
        if txn.country_code in HIGH_RISK_COUNTRIES:
            hits.append(RuleHit('R005_HIGH_RISK_COUNTRY', 1,
                                self.weights['R005_HIGH_RISK_COUNTRY'],
                                {'country': txn.country_code}))
 
        if txn.account_last_active_on is not None:
            idle = txn.occurred_at - txn.account_last_active_on
            if idle >= timedelta(days=self.dormancy_days):
                hits.append(RuleHit('R006_DORMANT_REACTIVATION', 1,
                                    self.weights['R006_DORMANT_REACTIVATION'],
                                    {'idle_days': idle.days}))
 
        return hits
 
 
def rule_score(hits: list[RuleHit]) -> int:
    """Capped additive score so a pile-up of small rules cannot exceed 100."""
    return min(100, sum(h.weight for h in hits))
 
 
def risk_band(score: int) -> str:
    if score >= 80:
        return 'critical'
    if score >= 55:
        return 'high'
    if score >= 35:
        return 'medium'
    return 'low'
 
 
def decision_for(band: str) -> str:
    return {'low': 'allow', 'medium': 'allow_monitor',
            'high': 'review', 'critical': 'block'}[band]
 
 
def dedup_key(account_id: str, codes: list[str], occurred_at: datetime) -> str:
    """Stable key so replays do not create duplicate alerts."""
    bucket = occurred_at.strftime('%Y%m%d%H')
    return f"{account_id}|{'+'.join(sorted(codes))}|{bucket}"
