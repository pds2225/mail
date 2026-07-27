import { describe, expect, it } from "vitest";
import {
  normalizeUrl,
  validateSiteEditInput,
  validateSiteInput,
} from "@/lib/site-validation";
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

  it("edits an existing site while preserving collector-specific fields", () => {
    const withCustomFields: SiteRecord[] = [
      {
        ...existing[0],
        max_pages: 7,
        selectors: { row: "ul li", title: "a.title" },
      },
    ];
    const result = validateSiteEditInput(
      {
        id: "bizinfo",
        name: "기업마당 새 이름",
        url: "https://www.bizinfo.go.kr/x",
        collectorType: "bizinfo_api",
        enabled: false,
        isAggregator: true,
        note: "변경 메모",
        selectorsRow: "div.notice",
        testCollect: false,
      },
      withCustomFields,
    );

    expect(result.ok).toBe(true);
    expect(result.normalized.id).toBe("bizinfo");
    expect(result.normalized.max_pages).toBe(7);
    expect(result.normalized.selectors).toEqual({
      row: "div.notice",
      title: "a.title",
    });
  });

  it("rejects edits for an unknown site id", () => {
    const result = validateSiteEditInput(
      {
        id: "missing",
        name: "없음",
        url: "https://example.com",
        collectorType: "html_table",
        enabled: true,
        isAggregator: false,
        note: "",
        testCollect: false,
      },
      existing,
    );
    expect(result.ok).toBe(false);
    expect(result.errors[0].field).toBe("id");
  });
});
