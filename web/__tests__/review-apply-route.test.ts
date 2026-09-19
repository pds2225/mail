import { gunzipSync } from "node:zlib";
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

import { POST } from "@/app/api/review/apply/route";

function request(body: unknown): Request {
  return new Request("https://example.test/api/review/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const existingFeedback = `${JSON.stringify({
  id: "notice-1",
  verdict: "X",
  tier: "C",
  source: "mail-feedback",
  title: "",
  first_seen: "2026-01-01T00:00:00Z",
  last_seen: "2026-01-01T00:00:00Z",
})}\n`;

describe("POST /api/review/apply", () => {
  beforeEach(() => {
    mocks.token = "";
    mocks.getRepoTextFile.mockReset();
    mocks.putRepoTextFile.mockReset();
    mocks.getRepoTextFile.mockResolvedValue({ sha: "base-sha", text: existingFeedback });
    mocks.putRepoTextFile.mockResolvedValue({
      sha: "commit-sha",
      htmlUrl: "https://github.com/pds2225/mail/blob/main/data/golden/feedback_labels.jsonl",
      commitUrl: "https://github.com/pds2225/mail/commit/commit-sha",
    });
  });

  it("returns a pending batch result without a token (does not commit)", async () => {
    const response = await POST(
      request({
        items: [
          { id: "notice-1", title: "AI 지원사업", verdict: "O" },
          { id: "notice-2", title: "제조 바우처", verdict: "X" },
        ],
      }),
    );
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.applied).toBe(false);
    expect(data.manualPasteRequired).toBe(true);
    expect(data.githubCommitUrl).toBe("https://github.com/pds2225/mail/new/main/.apply");
    expect(data.githubCommitUrl).not.toContain("value=");
    expect(data.githubCommitUrl.length).toBeLessThan(100);
    expect(data.pendingFilename).toBe("config-pending.json");
    const pending = JSON.parse(data.pendingContent);
    expect(pending.encoding).toBe("gzip-base64");
    const unpacked = JSON.parse(
      gunzipSync(Buffer.from(pending.packed_items, "base64")).toString("utf-8"),
    );
    expect(unpacked).toEqual([
      { id: "notice-1", title: "AI 지원사업", verdict: "O" },
      { id: "notice-2", title: "제조 바우처", verdict: "X" },
    ]);
    expect(data.notice).toContain("2건");
    expect(mocks.putRepoTextFile).not.toHaveBeenCalled();
  });

  it("keeps the GitHub URL short even for a 40-item long-title guest batch", async () => {
    const items = Array.from({ length: 40 }, (_, index) => ({
      id: `notice-${index + 1}`,
      title:
        `2026년 인공지능·데이터 기반 제조혁신 및 글로벌 사업화 지원사업 참여기업 모집공고 ${index + 1}차 `.repeat(
          3,
        ),
      verdict: index % 2 === 0 ? "O" : "X",
    }));

    const response = await POST(request({ items }));
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.applied).toBe(false);
    expect(data.githubCommitUrl).toBe("https://github.com/pds2225/mail/new/main/.apply");
    expect(data.githubCommitUrl).not.toContain("value=");
    expect(data.pendingContent.length).toBeGreaterThan(0);
  });

  it("writes every selected item in a single commit when a token is present", async () => {
    mocks.token = "fixture-token";
    const response = await POST(
      request({
        items: [
          { id: "notice-1", title: "AI 지원사업", verdict: "O" },
          { id: "notice-2", title: "제조 바우처", verdict: "X" },
        ],
      }),
    );
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.applied).toBe(true);
    expect(mocks.getRepoTextFile).toHaveBeenCalledTimes(1);
    expect(mocks.putRepoTextFile).toHaveBeenCalledTimes(1);

    const written = mocks.putRepoTextFile.mock.calls[0][0];
    expect(written.message).toContain("2건");
    const rows = written.text
      .trim()
      .split("\n")
      .map((line: string) => JSON.parse(line));
    const byId = Object.fromEntries(rows.map((row: { id: string }) => [row.id, row]));
    expect(byId["notice-1"].verdict).toBe("O");
    expect(byId["notice-1"].first_seen).toBe("2026-01-01T00:00:00Z");
    expect(byId["notice-2"].verdict).toBe("X");
    expect(byId["notice-2"].title).toBe("제조 바우처");
  });

  it("still accepts a single legacy {id,title,verdict} body", async () => {
    mocks.token = "fixture-token";
    const response = await POST(request({ id: "notice-3", title: "단일 항목", verdict: "O" }));
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.applied).toBe(true);
    const written = mocks.putRepoTextFile.mock.calls[0][0];
    expect(written.message).toContain("O notice-3");
  });

  it("rejects a payload with no valid items", async () => {
    const response = await POST(request({ items: [{ id: "bad id with spaces", verdict: "O" }] }));
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data.ok).toBe(false);
    expect(mocks.putRepoTextFile).not.toHaveBeenCalled();
  });

  it("returns 500 without claiming success when GitHub read fails", async () => {
    mocks.token = "fixture-token";
    mocks.getRepoTextFile.mockRejectedValue(new Error("fixture network failure"));
    const response = await POST(request({ items: [{ id: "notice-1", title: "x", verdict: "O" }] }));
    const data = await response.json();

    expect(response.status).toBe(500);
    expect(data.ok).toBe(false);
    expect(data.applied).not.toBe(true);
  });
});
