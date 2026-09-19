import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  token: "",
  pendingExists: true,
  getRepoTextFile: vi.fn(),
  putRepoTextFile: vi.fn(),
  repoTextFileExists: vi.fn(),
}));

vi.mock("@/lib/apply-auth", () => ({
  applyAuthError: vi.fn(() => null),
  githubApplyToken: vi.fn(() => mocks.token),
}));

vi.mock("@/lib/github-apply", () => ({
  getRepoTextFile: mocks.getRepoTextFile,
  githubBranch: vi.fn(() => "main"),
  putRepoTextFile: mocks.putRepoTextFile,
  repoTextFileExists: mocks.repoTextFileExists,
}));

import { POST } from "@/app/api/config/apply/route";

function request(body: unknown): Request {
  return new Request("https://example.test/api/config/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/config/apply tokenless fallback", () => {
  beforeEach(() => {
    mocks.token = "";
    mocks.pendingExists = true;
    mocks.getRepoTextFile.mockReset();
    mocks.putRepoTextFile.mockReset();
    mocks.repoTextFileExists.mockReset();
    mocks.repoTextFileExists.mockImplementation(async () => mocks.pendingExists);
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

  it("uses edit URL and separate payload when config-pending already exists", async () => {
    mocks.pendingExists = true;
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
    expect(data.pendingFileExists).toBe(true);
    expect(data.githubCommitUrl).toBe(
      "https://github.com/pds2225/mail/edit/main/.apply/config-pending.json",
    );
    expect(data.githubCommitUrl).not.toContain("value=");
    expect(JSON.parse(data.pendingContent)).toMatchObject({
      v: 1,
      resource: "group",
      id: "grp_demo",
      patch: { name: "Updated" },
    });
  });

  it("uses new URL with filename only when config-pending does not exist", async () => {
    mocks.pendingExists = false;
    const response = await POST(
      request({
        resource: "settings",
        patch: { days_back: 5 },
      }),
    );
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.pendingFileExists).toBe(false);
    expect(data.githubCommitUrl).toBe(
      "https://github.com/pds2225/mail/new/main/.apply?filename=config-pending.json",
    );
    expect(data.githubCommitUrl).not.toContain("value=");
    expect(JSON.parse(data.pendingContent)).toMatchObject({
      v: 1,
      resource: "settings",
      patch: { days_back: 5 },
    });
  });
});
