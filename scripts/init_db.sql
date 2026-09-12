-- ============================================================-- AegisFlow — M1 schema-- Applied automatically on first boot via docker-entrypoint-initdb.d-- ============================================================
 
CREATE EXTENSION IF NOT EXISTS pgcrypto;
 -- ============================================================-- MASTER DATA-- ============================================================
 
CREATE TABLE IF NOT EXISTS customers (
    customer_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_ref    VARCHAR(64) UNIQUE NOT NULL,
    full_name       VARCHAR(200) NOT NULL,
    date_of_birth   DATE,
    country_code    CHAR(2) NOT NULL,
    kyc_status      VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (kyc_status IN ('pending','verified','rejected','expired')),
    risk_rating     VARCHAR(10) NOT NULL DEFAULT 'medium'
                    CHECK (risk_rating IN ('low','medium','high')),
    is_pep          BOOLEAN NOT NULL DEFAULT FALSE,
    onboarded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
 
CREATE TABLE IF NOT EXISTS accounts (
    account_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     UUID NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    account_number  VARCHAR(34) UNIQUE NOT NULL,   -- IBAN-width
    account_type    VARCHAR(20) NOT NULL CHECK (account_type IN ('current','savings','card','wallet')),
    currency        CHAR(3) NOT NULL DEFAULT 'INR',
    opened_on       DATE NOT NULL,
    last_active_on  DATE,
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','dormant','frozen','closed'))
);
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);
 
CREATE TABLE IF NOT EXISTS counterparties (
    counterparty_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    beneficiary_ref VARCHAR(64) NOT NULL,
    beneficiary_name VARCHAR(200),
    country_code    CHAR(2),
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    txn_count       INT NOT NULL DEFAULT 0,
    UNIQUE (account_id, beneficiary_ref)
);
 -- ============================================================-- TRANSACTION LEDGER (immutable)-- ============================================================
 
CREATE TABLE IF NOT EXISTS transactions (
    txn_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_ref    VARCHAR(64) UNIQUE NOT NULL,
    account_id      UUID NOT NULL REFERENCES accounts(account_id),
    counterparty_id UUID REFERENCES counterparties(counterparty_id),
    channel         VARCHAR(20) NOT NULL CHECK (channel IN ('card','wire','upi','ach','atm')),
    direction       VARCHAR(6) NOT NULL CHECK (direction IN ('debit','credit')),
    amount          NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    currency        CHAR(3) NOT NULL DEFAULT 'INR',
    merchant_mcc    VARCHAR(4),
    country_code    CHAR(2),
    device_id       VARCHAR(80),
    ip_address      INET,
    occurred_at     TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_payload     JSONB
);
CREATE INDEX IF NOT EXISTS idx_txn_account_time ON transactions(account_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_txn_occurred ON transactions(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_txn_amount ON transactions(amount) WHERE amount > 100000;
 
CREATE TABLE IF NOT EXISTS velocity_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          UUID NOT NULL REFERENCES transactions(txn_id) ON DELETE CASCADE,
    txn_count_1m    INT NOT NULL DEFAULT 0,
    txn_count_1h    INT NOT NULL DEFAULT 0,
    txn_count_24h   INT NOT NULL DEFAULT 0,
    amount_sum_24h  NUMERIC(18,2) NOT NULL DEFAULT 0,
    distinct_cp_24h INT NOT NULL DEFAULT 0,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_velocity_txn ON velocity_snapshots(txn_id);
-- ============================================================ -- DETECTION-- ============================================================
 
CREATE TABLE IF NOT EXISTS rule_definitions (
    rule_code       VARCHAR(30) NOT NULL,
    version         INT NOT NULL,
    description     TEXT NOT NULL,
    weight          INT NOT NULL CHECK (weight BETWEEN 0 AND 100),
    params          JSONB NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rule_code, version)
);
 
CREATE TABLE IF NOT EXISTS rule_hits (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          UUID NOT NULL REFERENCES transactions(txn_id) ON DELETE CASCADE,
    rule_code       VARCHAR(30) NOT NULL,
    rule_version    INT NOT NULL,
    weight_applied  INT NOT NULL,
    evidence        JSONB NOT NULL DEFAULT '{}',
    fired_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (rule_code, rule_version) REFERENCES rule_definitions(rule_code, version)
);
CREATE INDEX IF NOT EXISTS idx_rule_hits_txn ON rule_hits(txn_id);
CREATE INDEX IF NOT EXISTS idx_rule_hits_code ON rule_hits(rule_code, fired_at DESC);
 
CREATE TABLE IF NOT EXISTS risk_assessments (
    txn_id          UUID PRIMARY KEY REFERENCES transactions(txn_id) ON DELETE CASCADE,
    rule_score      INT NOT NULL DEFAULT 0,
    model_score     DOUBLE PRECISION,           -- NULL until M2 model exists
    blended_score   INT NOT NULL,
    risk_band       VARCHAR(10) NOT NULL CHECK (risk_band IN ('low','medium','high','critical')),
    decision        VARCHAR(20) NOT NULL CHECK (decision IN ('allow','allow_monitor','review','block')),
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scorer_version  VARCHAR(40) NOT NULL DEFAULT 'm1-rules-only'
);
CREATE INDEX IF NOT EXISTS idx_risk_band ON risk_assessments(risk_band, scored_at DESC);
 -- ============================================================-- ALERTS, CASES, AUDIT-- ============================================================
 
CREATE TABLE IF NOT EXISTS alerts (
    alert_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    txn_id          UUID NOT NULL REFERENCES transactions(txn_id),
    account_id      UUID NOT NULL REFERENCES accounts(account_id),
    dedup_key       VARCHAR(160) NOT NULL,
    severity        VARCHAR(10) NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    headline        VARCHAR(300) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open','triaged','escalated','closed_true','closed_false')),
    raised_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (dedup_key)
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, raised_at DESC);
 
CREATE TABLE IF NOT EXISTS cases (
    case_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number     VARCHAR(20) UNIQUE NOT NULL,
    customer_id     UUID NOT NULL REFERENCES customers(customer_id),
    priority        VARCHAR(10) NOT NULL DEFAULT 'medium',
    status          VARCHAR(20) NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open','investigating','sar_filed','closed')),
    assigned_to     VARCHAR(80),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);
 
CREATE TABLE IF NOT EXISTS case_alerts (
    case_id         UUID NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    alert_id        UUID NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
    linked_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (case_id, alert_id)
);
 
CREATE TABLE IF NOT EXISTS case_notes (
    note_id         BIGSERIAL PRIMARY KEY,
    case_id         UUID NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    author          VARCHAR(80) NOT NULL,
    note_type       VARCHAR(20) NOT NULL DEFAULT 'comment',
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
 
CREATE TABLE IF NOT EXISTS watchlist_entries (
    entry_id        BIGSERIAL PRIMARY KEY,
    list_name       VARCHAR(40) NOT NULL,     -- 'ofac','un','internal'
    entity_name     VARCHAR(200) NOT NULL,
    entity_type     VARCHAR(20) NOT NULL DEFAULT 'individual',
    country_code    CHAR(2),
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_watchlist_name ON watchlist_entries(lower(entity_name));
 
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor           VARCHAR(80) NOT NULL,
    action          VARCHAR(50) NOT NULL,
    resource_type   VARCHAR(50) NOT NULL,
    resource_id     VARCHAR(100) NOT NULL,
    detail          JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id);