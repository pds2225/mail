import { maskEmail } from "./recipient-validation";

type GroupLike = {
  id?: string;
  name?: string;
  recipients?: unknown;
  [key: string]: unknown;
};

export function maskRecipientList(recipients: unknown): string[] {
  if (!Array.isArray(recipients)) return [];
  return recipients.map((r) => {
    if (typeof r !== "string") return "***";
    if (r.includes("[REDACTED]")) return "[REDACTED]";
    return r.includes("@") ? maskEmail(r) : "***";
  });
}

export function maskGroupsForApi(groups: unknown[]): GroupLike[] {
  return groups.map((g) => {
    const group = g as GroupLike;
    return {
      ...group,
      recipients: maskRecipientList(group.recipients),
    };
  });
}

export function maskSettingsForApi(settings: Record<string, unknown>): Record<string, unknown> {
  const out = { ...settings };
  if (Array.isArray(out.raw_all_recipients)) {
    out.raw_all_recipients = maskRecipientList(out.raw_all_recipients);
  }
  return out;
}
