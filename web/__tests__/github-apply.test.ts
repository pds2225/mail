import { describe, expect, it } from "vitest";
import { serializeSitesJson, parseSitesJson } from "@/lib/github-apply";
import { pendingApplyCommitUrl } from "@/lib/github-commit-url";
import {
  applyAuthError,
  applyStatus,
  APPLY_SECRET_HEADER,
  GITHUB_TOKEN_HEADER,
} from "@/lib/apply-auth";
import type { SiteRecord } from "@/lib/site-types";

const ENV_KEYS = [
  "CONFIG_APPLY_SECRET",
  "GITHUB_APPLY_TOKEN",
  "GITHUB_TOKEN",
  "AUTO_DEV_PAT",
] as const;

function withEnv(
  values: Partial<Record<(typeof ENV_KEYS)[number], string | undefined>>,
  fn: () => void,
) {
  const prev: Record<string, string | undefined> = {};
  for (const key of ENV_KEYS) prev[key] = process.env[key];
  try {
    for (const key of ENV_KEYS) {
      const next = key in values ? values[key] : undefined;
      if (next === undefined) delete process.env[key];
      else process.env[key] = next;
    }
    fn();
  } finally {
    for (const key of ENV_KEYS) {
      if (prev[key] === undefined) delete process.env[key];
      else process.env[key] = prev[key];
    }
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

describe("pendingApplyCommitUrl", () => {
  it("opens GitHub new-file for .apply/pending.json", () => {
    const url = pendingApplyCommitUrl({
      v: 1,
      mode: "add",
      site: {
        id: "demo",
        name: "Demo",
        type: "html_table",
        url: "https://example.com/demo",
        enabled: true,
        is_aggregator: false,
      },
    });
    expect(url).toContain("https://github.com/pds2225/mail/new/main/.apply?");
    expect(url).toContain("filename=pending.json");
    expect(url).toContain("example.com");
  });
});

describe("applyAuthError", () => {
  it("does not require a GitHub token when Vercel has no shared secret", () => {
    withEnv({}, () => {
      const req = new Request("https://example.test/api/sites/apply");
      expect(applyAuthError(req)).toBeNull();
      expect(applyStatus().mode).toBe("github-web");
      expect(applyStatus().applyReady).toBe(true);
    });
  });

  it("does not let a server GitHub token apply without CONFIG_APPLY_SECRET", () => {
    withEnv({ GITHUB_APPLY_TOKEN: "ghp_server" }, () => {
      const req = new Request("https://example.test/api/sites/apply", {
        headers: { [GITHUB_TOKEN_HEADER]: "ghp_client" },
      });
      expect(applyAuthError(req)).toBeNull();
      expect(applyStatus().mode).toBe("github-web");
    });
  });

  it("refuses mismatched shared secret even if a GitHub token is present", () => {
    withEnv({ CONFIG_APPLY_SECRET: "correct-secret", GITHUB_APPLY_TOKEN: "ghp_server" }, () => {
      const req = new Request("https://example.test/api/sites/apply", {
        headers: {
          [APPLY_SECRET_HEADER]: "wrong",
          [GITHUB_TOKEN_HEADER]: "ghp_client",
        },
      });
      expect(applyAuthError(req)).toMatch(/암호/);
    });
  });

  it("passes when shared secret and server token match", () => {
    withEnv({ CONFIG_APPLY_SECRET: "correct-secret", GITHUB_APPLY_TOKEN: "ghp_server" }, () => {
      const req = new Request("https://example.test/api/sites/apply", {
        headers: { [APPLY_SECRET_HEADER]: "correct-secret" },
      });
      expect(applyAuthError(req)).toBeNull();
      expect(applyStatus().mode).toBe("server");
      expect(applyStatus().applyReady).toBe(true);
    });
  });
});
