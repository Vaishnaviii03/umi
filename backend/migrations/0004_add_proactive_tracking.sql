-- UMI Phase 9: proactive (idle) conversation tracking.
-- Mirrors 0001-0003: idempotent, safe to run multiple times.
-- The backend enforces the idle policy on every proactive turn:
--   last_proactive_at          pins the cooldown between proactive openers,
--   proactive_count_last_hour  pins the rolling hourly cap.
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS last_proactive_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS proactive_count_last_hour INTEGER NOT NULL DEFAULT 0;