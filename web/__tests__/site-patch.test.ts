import { describe, expect, it } from "vitest";
import { buildSitesPatch, jsonPatchSnippet } from "@/lib/site-patch";
import type { SiteRecord } from "@/lib/site-types";

describe("sites.json patch", () => {
  it("appends one site", () => {
    const existing: SiteRecord[] = [
      {
        id: "a",
        name: "A",
        type: "html_table",
        url: "https://a.com",
        enabled: true,
        is_aggregator: false,
      },
    ];
    const add: SiteRecord = {
      id: "b",
      name: "B",
      type: "html_table",
      url: "https://b.com",
      enabled: true,
      is_aggregator: false,
    };
    expect(buildSitesPatch(existing, add)).toHaveLength(2);
    expect(buildSitesPatch(existing, add)[1].id).toBe("b");
  });

  it("jsonPatchSnippet is valid JSON", () => {
    const snippet = jsonPatchSnippet([], {
      id: "x",
      name: "X",
      type: "bizinfo_api",
      url: "https://x.com",
      enabled: true,
      is_aggregator: true,
    });
    expect(() => JSON.parse(snippet)).not.toThrow();
  });
});
