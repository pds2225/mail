import { describe, expect, it } from "vitest";
import { maskGroupsForApi, maskRecipientList } from "@/lib/config-mask";

describe("config mask", () => {
  it("masks email recipients", () => {
    const masked = maskRecipientList(["user@example.com", "[REDACTED]"]);
    expect(masked[1]).toBe("[REDACTED]");
    expect(masked[0]).not.toContain("user@");
    expect(masked[0]).toContain("@example.com");
  });

  it("masks groups for api", () => {
    const out = maskGroupsForApi([
      { id: "g1", name: "G", recipients: ["a@b.co", "x@y.z"] },
    ]);
    expect(out[0].recipients?.[0]).not.toBe("a@b.co");
  });
});
