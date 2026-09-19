-- UMI: multi-channel conversation threads.
-- Mirrors 0001: idempotent, safe to run multiple times. Existing rows keep
-- source='desktop' with a NULL conversation_key, which is the desktop
-- resolution path, so no backfill or data change is required.
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'desktop';
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS conversation_key TEXT;