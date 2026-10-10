-- Phase 6: token lifecycle metadata used by the email sync housekeeping job.
ALTER TABLE email_integrations
    ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_email_integrations_token_expiry
    ON email_integrations (token_expires_at)
    WHERE token_expires_at IS NOT NULL;
