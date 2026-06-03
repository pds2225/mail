import { describe, expect, it } from "vitest";
import { buildRecipientPacket } from "@/lib/packet-markdown";
import { validateRecipients } from "@/lib/recipient-validation";

describe("packet markdown", () => {
  it("masks recipient emails in approval packets", () => {
    const validation = validateRecipients([
      "alice.secret@example.com",
      "Alice.Secret@example.com",
      "not-email",
    ]);

    const packet = buildRecipientPacket({
      target: "group",
      groupId: "exports",
      groupName: "Export Alerts",
      added: ["alice.secret@example.com", "Alice.Secret@example.com", "not-email"],
      validation,
    });

    expect(packet).toContain("대상: groups.json");
    expect(packet).toContain("valid: 1건");
    expect(packet).toContain("rejected: 2건");
    expect(packet).not.toContain("alice.secret@example.com");
    expect(packet).not.toContain("Alice.Secret@example.com");
    expect(packet).toContain("al******@example.com");
    expect(packet).toContain("*** (형식 오류)");
  });
});
