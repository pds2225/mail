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
