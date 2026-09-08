/** Discord/Telegram integration status helpers (no React, node-testable). */

export type PlatformIntegration = {
  enabled: boolean;
  status: string;
  detail: string | null;
};

export type IntegrationsStatus = {
  discord: PlatformIntegration;
  telegram: PlatformIntegration;
};

export const INTEGRATION_PLATFORMS = ["discord", "telegram"] as const;
export type IntegrationPlatform = (typeof INTEGRATION_PLATFORMS)[number];

const LABELS: Record<IntegrationPlatform, string> = {
  discord: "Discord",
  telegram: "Telegram",
};

/** Human-friendly platform label for status chips. */
export function integrationLabel(platform: IntegrationPlatform): string {
  return LABELS[platform];
}

/** An integration is live (chip glows mint) when configured and healthy. */
export function integrationActive(
  integration: PlatformIntegration | null | undefined,
): boolean {
  if (!integration || !integration.enabled) return false;
  return integration.status !== "disabled" && integration.status !== "error";
}

/** Short human status for the chip tooltip, falling back to "off". */
export function integrationStatusLabel(
  integration: PlatformIntegration | null | undefined,
): string {
  if (!integration || !integration.enabled) return "off";
  if (integration.status === "connected") return "connected";
  return integration.status;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/** Fetch the backend integrations status; returns null when unreachable. */
export async function fetchIntegrationsStatus(): Promise<IntegrationsStatus | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/integrations/status`);
    if (!res.ok) return null;
    return (await res.json()) as IntegrationsStatus;
  } catch {
    return null;
  }
}