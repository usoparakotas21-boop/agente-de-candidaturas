-- Phase 5: Mercado Pago delivery ledger and server-only access.
-- The application also creates this table through SQLAlchemy startup; this
-- migration is safe to run independently in Supabase/PostgreSQL.
CREATE TABLE IF NOT EXISTS billing_webhook_events (
    id BIGSERIAL PRIMARY KEY,
    event_key VARCHAR(180) NOT NULL,
    payment_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'received',
    payload_hash VARCHAR(64) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 1,
    error_detail VARCHAR(1000),
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    CONSTRAINT uq_billing_webhook_event_key UNIQUE (event_key)
);
CREATE INDEX IF NOT EXISTS ix_billing_webhook_events_payment_id ON billing_webhook_events (payment_id);
CREATE INDEX IF NOT EXISTS ix_billing_webhook_events_status_received ON billing_webhook_events (status, received_at);
ALTER TABLE billing_webhook_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE billing_webhook_events FROM anon, authenticated;
