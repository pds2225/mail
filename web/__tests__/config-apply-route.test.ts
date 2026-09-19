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
  putRepoTextFile: mocks.putRepoTextFile,
}));

import { POST } from "@/app/api/config/apply/route";

function request(body: unknown): Request {
  return new Request("https://example.test/api/config/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/config/apply tokenless direct-file fallback", () => {
  beforeEach(() => {
    mocks.token = "";
    mocks.getRepoTextFile.mockReset();
    mocks.putRepoTextFile.mockReset();
    mocks.getRepoTextFile.mockImplementation(async (path: string) => {
      if (path === "config/groups.json") {
        return {
          sha: "group-sha",
          text: JSON.stringify([{ id: "grp_demo", name: "Demo", active: true }]),
        };
      }
      if (path === "config/settings.json") {
        return { sha: "settings-sha", text: JSON.stringify({ days_back: 3 }) };
      }
      throw new Error(`unexpected path: ${path}`);
    });
  });

  it("returns full updated groups.json and direct edit URL", async () => {
    const response = await POST(
      request({
        resource: "group",
        id: "grp_demo",
        patch: { name: "Updated" },
      }),
    );
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.applied).toBe(false);
    expect(data.manualPasteRequired).toBe(true);
    expect(data.manualFilePath).toBe("config/groups.json");
    expect(data.githubCommitUrl).toBe(
      "https://github.com/pds2225/mail/edit/main/config/groups.json",
    );
    expect(data.githubCommitUrl).not.toContain("value=");
    expect(data.githubCommitUrl).not.toContain(".apply/config-pending.json");
    expect(JSON.parse(data.manualContent)).toEqual([
      { id: "grp_demo", name: "Updated", active: true },
    ]);
  });

  it("returns full updated settings.json and direct edit URL", async () => {
    const response = await POST(
      request({
        resource: "settings",
        patch: { days_back: 5 },
      }),
    );
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.manualFilePath).toBe("config/settings.json");
    expect(data.githubCommitUrl).toBe(
      "https://github.com/pds2225/mail/edit/main/config/settings.json",
    );
    expect(data.githubCommitUrl).not.toContain("value=");
    expect(data.githubCommitUrl).not.toContain(".apply/config-pending.json");
    expect(JSON.parse(data.manualContent)).toMatchObject({ days_back: 5 });
  });
});
