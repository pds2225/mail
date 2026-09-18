import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  token: "",
  getRepoTextFile: vi.fn(),
  putRepoTextFile: vi.fn(),
}));

vi.mock("@/lib/apply-auth", () => ({
  applyAuthError: vi.fn(() => null),
  githubApplyToken: vi.fn(() => mocks.token),
}));

vi.mock("@/lib/github-apply", () => ({
  getRepoTextFile: mocks.getRepoTextFile,
  githubBranch: vi.fn(() => "main"),
  parseSitesJson: (text: string) => JSON.parse(text),
  putRepoTextFile: mocks.putRepoTextFile,
  serializeSitesJson: (sites: unknown[]) => `${JSON.stringify(sites)}\n`,
}));

import { POST } from "@/app/api/sites/apply/route";

const existing = [
  {
    id: "demo",
    name: "Demo",
    type: "html_table",
    url: "https://example.com/demo",
    enabled: true,
    is_aggregator: false,
    note: "keep",
  },
  {
    id: "other",
    name: "Other",
    type: "html_table",
    url: "https://example.com/other",
    enabled: false,
    is_aggregator: false,
  },
];

function request(body: unknown): Request {
  return new Request("https://example.test/api/sites/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function updateBody(enabled: unknown) {
  return {
    mode: "update",
    id: "demo",
    name: "Demo",
    url: "https://example.com/demo",
    collectorType: "html_table",
    enabled,
    isAggregator: false,
    note: "keep",
    selectorsRow: "",
    testCollect: false,
  };
}

describe("POST /api/sites/apply", () => {
  beforeEach(() => {
    mocks.token = "";
    mocks.getRepoTextFile.mockReset();
    mocks.putRepoTextFile.mockReset();
    mocks.getRepoTextFile.mockResolvedValue({
      sha: "base-sha",
      text: JSON.stringify(existing),
    });
    mocks.putRepoTextFile.mockResolvedValue({
      sha: "commit-sha",
      htmlUrl: "https://github.com/pds2225/mail/blob/main/config/sites.json",
      commitUrl: "https://github.com/pds2225/mail/commit/commit-sha",
    });
  });

  it("returns an explicit pending result without a token", async () => {
    const response = await POST(request(updateBody(false)));
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.applied).toBe(false);
    expect(data.pending).toBe(true);
    expect(data.site.enabled).toBe(false);
    expect(data.githubCommitUrl).toContain("filename=pending.json");
    expect(mocks.putRepoTextFile).not.toHaveBeenCalled();
  });

  it("uses the token path without losing enabled or other sites", async () => {
    mocks.token = "fixture-token";
    const response = await POST(request(updateBody(false)));
    const data = await response.json();
    const written = JSON.parse(mocks.putRepoTextFile.mock.calls[0][0].text);

    expect(response.status).toBe(200);
    expect(data.applied).toBe(true);
    expect(data.pending).toBeUndefined();
    expect(written[0].enabled).toBe(false);
    expect(written[0].note).toBe("keep");
    expect(written[1]).toEqual(existing[1]);
  });

  it("rejects a malformed enabled payload", async () => {
    const response = await POST(request(updateBody("false")));
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data.validation.errors.some((error: { field: string }) => error.field === "enabled")).toBe(true);
    expect(mocks.putRepoTextFile).not.toHaveBeenCalled();
  });

  it("returns 500 without claiming success when GitHub read fails", async () => {
    mocks.getRepoTextFile.mockRejectedValue(new Error("fixture network failure"));
    const response = await POST(request(updateBody(false)));
    const data = await response.json();

    expect(response.status).toBe(500);
    expect(data.ok).toBe(false);
    expect(data.applied).not.toBe(true);
  });
});
