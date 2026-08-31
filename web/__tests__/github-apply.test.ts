import { describe, expect, it } from "vitest";
import { serializeSitesJson, parseSitesJson } from "@/lib/github-apply";
import { applyAuthError, APPLY_SECRET_HEADER } from "@/lib/apply-auth";
import type { SiteRecord } from "@/lib/site-types";

function withEnv(secret: string | undefined, token: string | undefined, fn: () => void) {
  const prevSecret = process.env.CONFIG_APPLY_SECRET;
  const prevToken = process.env.GITHUB_APPLY_TOKEN;
  try {
    if (secret === undefined) delete process.env.CONFIG_APPLY_SECRET;
    else process.env.CONFIG_APPLY_SECRET = secret;
    if (token === undefined) delete process.env.GITHUB_APPLY_TOKEN;
    else process.env.GITHUB_APPLY_TOKEN = token;
    fn();
  } finally {
    if (prevSecret === undefined) delete process.env.CONFIG_APPLY_SECRET;
    else process.env.CONFIG_APPLY_SECRET = prevSecret;
    if (prevToken === undefined) delete process.env.GITHUB_APPLY_TOKEN;
    else process.env.GITHUB_APPLY_TOKEN = prevToken;
  }
}

describe("serializeSitesJson", () => {
  it("pretty-prints with trailing newline", () => {
    const sites: SiteRecord[] = [
      {
        id: "a",
        name: "A",
        type: "html_table",
        url: "https://a.example",
        enabled: true,
        is_aggregator: false,
      },
    ];
    const text = serializeSitesJson(sites);
    expect(text.endsWith("\n")).toBe(true);
    expect(parseSitesJson(text)).toEqual(sites);
  });
});

describe("applyAuthError", () => {
  it("refuses when secret env is missing", () => {
    withEnv(undefined, "ghs_test", () => {
      const req = new Request("https://example.test/api/sites/apply", {
        headers: { [APPLY_SECRET_HEADER]: "x" },
      });
      expect(applyAuthError(req)).toMatch(/CONFIG_APPLY_SECRET/);
    });
  });

  it("refuses mismatched secret", () => {
    withEnv("correct-secret", "ghs_test", () => {
      const req = new Request("https://example.test/api/sites/apply", {
        headers: { [APPLY_SECRET_HEADER]: "wrong" },
      });
      expect(applyAuthError(req)).toMatch(/암호/);
    });
  });

  it("passes when secret and token match", () => {
    withEnv("correct-secret", "ghs_test", () => {
      const req = new Request("https://example.test/api/sites/apply", {
        headers: { [APPLY_SECRET_HEADER]: "correct-secret" },
      });
      expect(applyAuthError(req)).toBeNull();
    });
  });
});
