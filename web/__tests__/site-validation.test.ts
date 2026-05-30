import { describe, expect, it } from "vitest";
import { validateSiteInput, normalizeUrl } from "@/lib/site-validation";
import type { SiteRecord } from "@/lib/site-types";

const existing: SiteRecord[] = [
  {
    id: "bizinfo",
    name: "기업마당",
    type: "bizinfo_api",
    url: "https://www.bizinfo.go.kr/x",
    enabled: true,
    is_aggregator: true,
  },
];

describe("site validation", () => {
  it("rejects missing name and invalid url", () => {
    const r = validateSiteInput(
      {
        name: "",
        url: "ftp://bad.com",
        category: "기타",
        collectorType: "html_table",
        enabled: true,
        isAggregator: false,
        note: "",
        testCollect: false,
      },
      existing,
    );
    expect(r.ok).toBe(false);
    expect(r.errors.length).toBeGreaterThan(0);
  });

  it("rejects duplicate url", () => {
    const r = validateSiteInput(
      {
        name: "새 사이트",
        url: "https://www.bizinfo.go.kr/x",
        category: "통합포털",
        collectorType: "html_table",
        enabled: true,
        isAggregator: true,
        note: "",
        testCollect: false,
      },
      existing,
    );
    expect(r.ok).toBe(false);
  });

  it("accepts valid proposal", () => {
    const r = validateSiteInput(
      {
        name: "테스트 TP",
        url: "https://example.com/notices",
        category: "지자체/TP",
        collectorType: "html_table",
        enabled: true,
        isAggregator: false,
        note: "테스트",
        testCollect: false,
      },
      existing,
    );
    expect(r.ok).toBe(true);
    expect(r.normalized.id).toBeTruthy();
  });

  it("normalizes url whitespace", () => {
    expect(normalizeUrl("  https://a.com/x  ")).toBe("https://a.com/x");
  });
});
