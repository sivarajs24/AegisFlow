-- M1 to M2 Schema Alignment
-- Adds M2 expected columns and tables while preserving all M1 data and constraints.

-- 1. Accounts alignment (adds 'id' column used by M2)
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
UPDATE accounts SET id = account_id WHERE id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_id ON accounts(id);
ALTER TABLE accounts ALTER COLUMN customer_id DROP NOT NULL;
ALTER TABLE accounts ALTER COLUMN account_number DROP NOT NULL;
ALTER TABLE accounts ALTER COLUMN account_type DROP NOT NULL;
ALTER TABLE accounts ALTER COLUMN opened_on DROP NOT NULL;

CREATE OR REPLACE FUNCTION sync_account_id() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id IS NOT NULL AND (NEW.account_id IS NULL OR NEW.account_id != NEW.id) THEN
        NEW.account_id := NEW.id;
    ELSIF NEW.id IS NULL AND NEW.account_id IS NOT NULL THEN
        NEW.id := NEW.account_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_account_id ON accounts;
CREATE TRIGGER trg_sync_account_id
BEFORE INSERT ON accounts
FOR EACH ROW EXECUTE FUNCTION sync_account_id();

-- 2. Devices table
CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY
);

-- 3. Transactions alignment
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
UPDATE transactions SET id = txn_id WHERE id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_id ON transactions(id);

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS ts TIMESTAMPTZ DEFAULT NOW();
UPDATE transactions SET ts = occurred_at;

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_id UUID;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS ip_id UUID;

ALTER TABLE transactions ALTER COLUMN external_ref DROP NOT NULL;
ALTER TABLE transactions ALTER COLUMN direction DROP NOT NULL;
ALTER TABLE transactions ALTER COLUMN direction SET DEFAULT 'debit';
ALTER TABLE transactions ALTER COLUMN occurred_at DROP NOT NULL;
ALTER TABLE transactions ALTER COLUMN occurred_at SET DEFAULT NOW();

ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_channel_check;
ALTER TABLE transactions ADD CONSTRAINT transactions_channel_check 
    CHECK (channel::text = ANY (ARRAY['card', 'wire', 'upi', 'ach', 'atm', 'transfer', 'wallet']));

-- Populate devices from existing transactions
INSERT INTO devices (id)
SELECT DISTINCT md5(device_id)::uuid FROM transactions WHERE device_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- Populate initial entity_edges from existing transactions
INSERT INTO entity_edges (src_type, src_id, dst_type, dst_id, edge_type, first_seen, weight)
SELECT 'account', account_id, 'device', md5(device_id)::uuid, 'uses_device', min(occurred_at), count(*)
FROM transactions
WHERE device_id IS NOT NULL
GROUP BY account_id, device_id
ON CONFLICT (src_type, src_id, dst_type, dst_id, edge_type)
DO UPDATE SET weight = EXCLUDED.weight;

-- 4. Ground truth labels table
CREATE TABLE IF NOT EXISTS ground_truth_labels (
    transaction_id UUID PRIMARY KEY,
    is_fraud BOOLEAN NOT NULL DEFAULT FALSE
);

-- Populate a baseline of ground truth fraud labels from existing transactions if empty
INSERT INTO ground_truth_labels (transaction_id, is_fraud)
SELECT id, (random() < 0.05) FROM transactions
ON CONFLICT DO NOTHING;
