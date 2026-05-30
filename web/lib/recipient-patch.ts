import { maskEmail } from "./recipient-validation";

export type GroupRecord = {
  id: string;
  name: string;
  recipients?: string[];
  [key: string]: unknown;
};

/** Merge valid new emails into group recipients (dedupe, case-insensitive). */
export function mergeGroupRecipients(
  existing: string[] | undefined,
  toAdd: string[],
): string[] {
  const out: string[] = [...(existing || [])];
  const seen = new Set(out.map((e) => e.toLowerCase()));
  for (const email of toAdd) {
    const key = email.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(email);
  }
  return out;
}

/** PR 패킷용: 기존 수신자 노출 없이 append 목록만 포함. */
export function buildGroupRecipientsAppendPatch(
  group: GroupRecord,
  toAdd: string[],
): string {
  return JSON.stringify(
    {
      file: "groups.json",
      instruction: "해당 그룹 recipients 배열 끝에 append 항목만 추가",
      groupId: group.id,
      groupName: group.name,
      append: toAdd,
    },
    null,
    2,
  );
}

export function buildRawAllRecipientsAppendPatch(toAdd: string[]): string {
  return JSON.stringify(
    {
      file: "settings.json",
      instruction: "raw_all_recipients 배열 끝에 append 항목만 추가",
      append: toAdd,
    },
    null,
    2,
  );
}

export function maskedAddList(emails: string[]): string {
  return emails.map((e) => `- ${maskEmail(e)}`).join("\n");
}
