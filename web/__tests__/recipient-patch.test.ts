import { describe, expect, it } from "vitest";
import {
  buildGroupRecipientsAppendPatch,
  mergeGroupRecipients,
} from "@/lib/recipient-patch";

describe("recipient patch", () => {
  it("merges without duplicate", () => {
    const r = mergeGroupRecipients(["a@x.com"], ["A@x.com", "b@y.com"]);
    expect(r).toEqual(["a@x.com", "b@y.com"]);
  });

  it("append patch does not include existing list", () => {
    const snippet = buildGroupRecipientsAppendPatch(
      { id: "g1", name: "G", recipients: ["secret@old.com"] },
      ["new@x.com"],
    );
    const parsed = JSON.parse(snippet);
    expect(parsed.append).toEqual(["new@x.com"]);
    expect(JSON.stringify(parsed)).not.toContain("secret@old.com");
  });
});
