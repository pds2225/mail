import { describe, expect, it } from "vitest";
import {
  maskEmail,
  planRecipientUpdate,
  publicRecipientEntries,
  recipientEntryId,
  validateRecipients,
} from "@/lib/recipient-validation";

describe("recipient validation", () => {
  it("dedupes and rejects invalid", () => {
    const r = validateRecipients([
      "a@example.com",
      "A@example.com",
      "not-email",
    ]);
    expect(r.valid).toEqual(["a@example.com"]);
    expect(r.rejected.length).toBe(2);
  });

  it("masks email", () => {
    const m = maskEmail("abcdef@example.com");
    expect(m).toContain("@example.com");
    expect(m).not.toContain("abcdef");
  });

  it("exposes masked entries with opaque removal ids", () => {
    const entries = publicRecipientEntries(["alice.secret@example.com"]);
    expect(entries).toEqual([
      {
        id: recipientEntryId("alice.secret@example.com"),
        masked: "al******@example.com",
      },
    ]);
    expect(JSON.stringify(entries)).not.toContain("alice.secret@example.com");
  });

  it("plans additions and masked-id removals without mutating the source", () => {
    const existing = ["old@example.com", "keep@example.com"];
    const plan = planRecipientUpdate(
      existing,
      ["new@example.com"],
      [recipientEntryId("old@example.com")],
    );

    expect(plan.ok).toBe(true);
    expect(plan.added).toEqual(["new@example.com"]);
    expect(plan.removed).toEqual(["old@example.com"]);
    expect(plan.next).toEqual(["keep@example.com", "new@example.com"]);
    expect(existing).toEqual(["old@example.com", "keep@example.com"]);
  });

  it("rejects duplicate additions and unknown removals", () => {
    const plan = planRecipientUpdate(
      ["same@example.com"],
      ["SAME@example.com"],
      ["missing-token"],
    );
    expect(plan.ok).toBe(false);
    expect(plan.rejected.map((item) => item.reason)).toEqual(
      expect.arrayContaining(["이미 등록됨", "제거 대상을 찾을 수 없음"]),
    );
  });
});
