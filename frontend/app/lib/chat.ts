/**
 * Pure helpers for the chat/session pipeline. Kept free of React/DOM so they
 * can be unit-tested without a browser (node --test).
 */

export const SESSION_STORAGE_KEY = "umi_conversation_id";

export type ChatRequestBody = {
  message: string;
  conversation_id: string | null;
  voice: boolean;
  proactive: boolean;
};

export type SessionInfo = {
  conversationId: string | null;
  resumed: boolean;
  greetingOwed: boolean;
  greetingNew: boolean;
  idle: {
    enabled: boolean;
    thresholdSeconds: number;
    cooldownSeconds: number;
    maxPromptsPerHour: number;
    startHour: number;
    endHour: number;
  } | null;
};

export type StorageLike = {
  getItem?: (key: string) => string | null;
  setItem?: (key: string, value: string) => void;
  removeItem?: (key: string) => void;
};

/**
 * Build the request body shared by the streaming and legacy chat endpoints.
 * `voice` lets the backend tune replies for speech (concise, fast model,
 * shorter history). `proactive` marks an idle opener with no user message.
 */
export function chatRequestBody(
  message: string,
  conversationId: string | null,
  voice: boolean,
  proactive = false,
): ChatRequestBody {
  return { message, conversation_id: conversationId, voice, proactive };
}

export function isUuidLike(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    value ?? "",
  );
}

export function readStoredConversationId(storage: StorageLike | null): string | null {
  const raw = storage?.getItem?.(SESSION_STORAGE_KEY) ?? null;
  if (!raw) return null;
  return isUuidLike(raw) ? raw : null;
}

export function storeConversationId(storage: StorageLike | null, id: string | null): void {
  if (!storage?.setItem) return;
  if (id) {
    storage.setItem(SESSION_STORAGE_KEY, id);
  } else {
    storage.removeItem?.(SESSION_STORAGE_KEY);
  }
}

/**
 * Normalize a GET /session payload defensively (the backend may be an older
 * version or degraded). Unknown/missing fields fall back to safe defaults.
 */
export function parseSessionResponse(data: unknown): SessionInfo {
  const obj = (data ?? {}) as Record<string, unknown>;
  const greeting = (obj.greeting ?? {}) as Record<string, unknown>;
  const idle = (obj.idle ?? null) as Record<string, unknown> | null;
  return {
    conversationId: typeof obj.conversation_id === "string" ? obj.conversation_id : null,
    resumed: obj.resumed === true,
    greetingOwed: greeting.owed === true,
    greetingNew: greeting.new === true,
    idle:
      idle && typeof idle.threshold_seconds === "number"
        ? {
            enabled: idle.enabled !== false,
            thresholdSeconds: idle.threshold_seconds,
            cooldownSeconds: typeof idle.cooldown_seconds === "number" ? idle.cooldown_seconds : 0,
            maxPromptsPerHour:
              typeof idle.max_prompts_per_hour === "number" ? idle.max_prompts_per_hour : 0,
            startHour: typeof idle.start_hour === "number" ? idle.start_hour : 0,
            endHour: typeof idle.end_hour === "number" ? idle.end_hour : 24,
          }
        : null,
  };
}