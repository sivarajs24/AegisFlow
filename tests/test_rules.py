from datetime import datetime, timedelta, timezone
from decimal import Decimal
 
import pytest
 
from libs.aegis_domain.rules import (
    RuleSet, Transaction, Velocity, dedup_key, decision_for, risk_band, rule_score,
)
 
NOW = datetime(2026, 9, 11, 10, 30, tzinfo=timezone.utc)
 
 
def txn(**over):
    base = dict(external_ref='T1', account_id='A1', amount=Decimal('1000'),
                currency='INR', channel='wire', direction='debit',
                country_code='IN', occurred_at=NOW)
    base.update(over)
    return Transaction(**base)
 
 
def test_clean_transaction_produces_no_hits():
    assert RuleSet().evaluate(txn(), Velocity()) == []
 
 
def test_high_value_fires_at_threshold():
    hits = RuleSet().evaluate(txn(amount=Decimal('500000')), Velocity())
    assert [h.code for h in hits] == ['R001_HIGH_VALUE']
 
 
def test_velocity_fires_above_limit_only():
    rs = RuleSet()
    assert rs.evaluate(txn(), Velocity(txn_count_1h=12)) == []
    assert rs.evaluate(txn(), Velocity(txn_count_1h=13))[0].code == 'R002_VELOCITY_1H'
 
 
def test_structuring_needs_both_count_and_sum():
    rs = RuleSet()
    only_sum = Velocity(sub_threshold_count_24h=1, amount_sum_24h=Decimal('2000000'))
    assert rs.evaluate(txn(), only_sum) == []
    both = Velocity(sub_threshold_count_24h=4, amount_sum_24h=Decimal('2000000'))
    assert rs.evaluate(txn(), both)[0].code == 'R003_STRUCTURING'
 
 
def test_new_beneficiary_requires_material_amount():
    rs = RuleSet()
    recent = NOW - timedelta(days=2)
    small = txn(amount=Decimal('5000'), beneficiary_first_seen_at=recent)
    assert rs.evaluate(small, Velocity()) == []
    large = txn(amount=Decimal('250000'), beneficiary_first_seen_at=recent)
    assert 'R004_NEW_BENEFICIARY' in [h.code for h in rs.evaluate(large, Velocity())]
 
 
def test_dormant_reactivation():
    rs = RuleSet()
    t = txn(account_last_active_on=NOW - timedelta(days=200))
    assert 'R006_DORMANT_REACTIVATION' in [h.code for h in rs.evaluate(t, Velocity())]
 
 
@pytest.mark.parametrize('score,band', [(0, 'low'), (34, 'low'), (35, 'medium'),
                                        (55, 'high'), (80, 'critical'), (100, 'critical')])
def test_band_boundaries(score, band):
    assert risk_band(score) == band
 
 
def test_score_is_capped_at_100():
    t = txn(amount=Decimal('900000'), country_code='KP',
            beneficiary_first_seen_at=NOW - timedelta(days=1),
            account_last_active_on=NOW - timedelta(days=400))
    v = Velocity(txn_count_1h=40, sub_threshold_count_24h=9,
                 amount_sum_24h=Decimal('5000000'))
    assert rule_score(RuleSet().evaluate(t, v)) == 100
 
 
def test_decision_mapping():
    assert decision_for('critical') == 'block'
    assert decision_for('low') == 'allow'
 
 
def test_dedup_key_is_order_independent_and_hour_bucketed():
    a = dedup_key('A1', ['R002_VELOCITY_1H', 'R001_HIGH_VALUE'], NOW)
    b = dedup_key('A1', ['R001_HIGH_VALUE', 'R002_VELOCITY_1H'], NOW + timedelta(minutes=20))
    assert a == b
