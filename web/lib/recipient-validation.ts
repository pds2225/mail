import { createHash } from "node:crypto";

const EMAIL_RE = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/;

export function maskEmail(email: string): string {
  const trimmed = (email || "").trim();
  const at = trimmed.indexOf("@");
  if (at <= 0) return "***";
  const local = trimmed.slice(0, at);
  const domain = trimmed.slice(at + 1);
  const masked =
    local.length <= 2 ? `${local[0] || ""}*` : `${local.slice(0, 2)}${"*".repeat(Math.min(local.length - 2, 6))}`;
  return `${masked}@${domain}`;
}

export function validateRecipients(raw: string[]): {
  valid: string[];
  rejected: { value: string; reason: string }[];
  masked: string[];
} {
  const valid: string[] = [];
  const rejected: { value: string; reason: string }[] = [];
  const seen = new Set<string>();

  for (const item of raw) {
    const email = (item || "").trim();
    if (!email) continue;
    const key = email.toLowerCase();
    if (seen.has(key)) {
      rejected.push({ value: email, reason: "중복" });
      continue;
    }
    seen.add(key);
    if (!EMAIL_RE.test(email)) {
      rejected.push({ value: email, reason: "형식 오류" });
      continue;
    }
    valid.push(email);
  }

  return { valid, rejected, masked: valid.map(maskEmail) };
}

export type PublicRecipientEntry = {
  id: string;
  masked: string;
};

export type RecipientUpdatePlan = {
  ok: boolean;
  beforeCount: number;
  afterCount: number;
  added: string[];
  removed: string[];
  next: string[];
  rejected: { value: string; reason: string }[];
};

export function recipientEntryId(email: string): string {
  return createHash("sha256").update(email.trim().toLowerCase()).digest("hex");
}

export function publicRecipientEntries(raw: unknown): PublicRecipientEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((value): value is string => typeof value === "string" && value.includes("@"))
    .map((email) => ({ id: recipientEntryId(email), masked: maskEmail(email) }));
}

export function publicRecipientValidation(
  validation: ReturnType<typeof validateRecipients>,
): {
  validCount: number;
  rejected: { reason: string }[];
  masked: string[];
} {
  return {
    validCount: validation.valid.length,
    rejected: validation.rejected.map(({ reason }) => ({ reason })),
    masked: validation.masked,
  };
}

export function planRecipientUpdate(
  existingRaw: unknown,
  additionsRaw: string[],
  removeEntryIds: string[],
): RecipientUpdatePlan {
  const existing = Array.isArray(existingRaw)
    ? existingRaw.filter((value): value is string => typeof value === "string" && Boolean(value.trim()))
    : [];
  const existingByKey = new Map(existing.map((email) => [email.trim().toLowerCase(), email.trim()]));
  const existingById = new Map(existing.map((email) => [recipientEntryId(email), email.trim()]));
  const validation = validateRecipients(additionsRaw);
  const rejected = [...validation.rejected];
  const removeSet = new Set<string>();
  const removed: string[] = [];

  for (const entryId of new Set(removeEntryIds.filter(Boolean))) {
    const email = existingById.get(entryId);
    if (!email) {
      rejected.push({ value: entryId, reason: "제거 대상을 찾을 수 없음" });
      continue;
    }
    const key = email.toLowerCase();
    if (!removeSet.has(key)) {
      removeSet.add(key);
      removed.push(email);
    }
  }

  const added: string[] = [];
  for (const email of validation.valid) {
    const key = email.toLowerCase();
    if (existingByKey.has(key) && !removeSet.has(key)) {
      rejected.push({ value: email, reason: "이미 등록됨" });
      continue;
    }
    if (removeSet.has(key)) {
      rejected.push({ value: email, reason: "동시에 추가·제거할 수 없음" });
      continue;
    }
    added.push(email);
  }

  const next = existing
    .filter((email) => !removeSet.has(email.trim().toLowerCase()))
    .concat(added);

  return {
    ok: rejected.length === 0,
    beforeCount: existing.length,
    afterCount: next.length,
    added,
    removed,
    next,
    rejected,
  };
}
