import { describe, expect, it } from "vitest";
import { maskEmail, validateRecipients } from "@/lib/recipient-validation";

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
});
