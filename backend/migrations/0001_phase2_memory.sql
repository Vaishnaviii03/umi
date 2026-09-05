-- UMI Phase 2: persist conversations + memories
-- Reconciles the Phase 2 SQLAlchemy models with the pre-existing scaffold.
-- Idempotent; safe to run multiple times.

-- Memory rows can originate from a conversation, but can also be standalone.
ALTER TABLE memories
    ADD COLUMN IF NOT EXISTS source_conversation_id uuid
    REFERENCES conversations (id) ON DELETE SET NULL;

-- New memories default to a generic type instead of requiring one.
ALTER TABLE memories
    ALTER COLUMN memory_type SET DEFAULT 'fact';
UPDATE memories SET memory_type = 'fact' WHERE memory_type IS NULL;

-- UMI always writes a reply body for assistant and user messages.
ALTER TABLE messages
    ALTER COLUMN content SET NOT NULL;