-- UMI Phase 9: greeting-once entitlement.
-- Mirrors 0001/0002: idempotent, safe to run multiple times. NULL means the
-- owner has not been greeted for this conversation; claim_greeting stamps it so
-- subsequent desktop launches inside the greeting window stay silent.
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS last_greeted_at TIMESTAMPTZ;