import { describe, expect, it } from "vitest";
import {
  buildRecipientPacket,
  buildSiteUpdatePacket,
} from "@/lib/packet-markdown";
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

    expect(packet).toContain("대상: config/groups.json");
    expect(packet).toContain("valid: 1건");
    expect(packet).toContain("rejected: 2건");
    expect(packet).not.toContain("alice.secret@example.com");
    expect(packet).not.toContain("Alice.Secret@example.com");
    expect(packet).toContain("al******@example.com");
    expect(packet).toContain("*** (형식 오류)");
  });

  it("includes masked additions and removals with counts", () => {
    const validation = validateRecipients(["new.person@example.com"]);
    const packet = buildRecipientPacket({
      target: "raw_all",
      added: ["new.person@example.com"],
      removed: ["old.person@example.com"],
      beforeCount: 2,
      afterCount: 2,
      validation,
    });

    expect(packet).toContain("수신자 수: 2건 → 2건");
    expect(packet).toContain("ne******@example.com");
    expect(packet).toContain("ol******@example.com");
    expect(packet).not.toContain("new.person@example.com");
    expect(packet).not.toContain("old.person@example.com");
  });

  it("builds an existing-site update packet", () => {
    const before = {
      id: "site-a",
      name: "기존",
      type: "html_table",
      url: "https://example.com",
      enabled: true,
      is_aggregator: false,
    };
    const after = { ...before, name: "변경", enabled: false };
    const packet = buildSiteUpdatePacket({
      branch: "chore/site-update-site-a",
      before,
      after,
      validation: {
        ok: true,
        errors: [],
        warnings: [],
        normalized: after,
        checks: {
          collectorRegistered: true,
          urlReachable: null,
          dateUnknownRisk: "높음",
          dryRunReady: true,
          stableIdNote: "stable",
        },
      },
      urlReachable: null,
    });

    expect(packet).toContain("SITE_UPDATE_PR_PACKET");
    expect(packet).toContain("`enabled`");
    expect(packet).toContain("`name`");
    expect(packet).toContain("\"name\": \"변경\"");
  });
});
