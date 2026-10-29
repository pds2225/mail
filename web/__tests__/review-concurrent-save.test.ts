import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Exercise the real route and GitHub CAS helper; only auth and HTTP are fixtures.
vi.mock("@/lib/apply-auth", () => ({
  applyAuthError: () => null,
  githubApplyToken: () => "fixture-token",
}));

import { POST } from "@/app/api/review/apply/route";

const path = "/repos/pds2225/mail/contents/data/golden/feedback_labels.jsonl";
const original = { id: "notice-a", verdict: "X", first_seen: "2026-01-01T00:00:00Z" };
const concurrent = { id: "notice-b", verdict: "X", source: "mail-feedback", extra: "keep me" };
const encode = (rows: object[]) => rows.map((row) => JSON.stringify(row)).join("\n") + "\n";
const selection = () => new Request("https://example.test/api/review/apply", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ items: [{ id: "notice-a", title: "Selected", verdict: "O" }] }),
});

describe("MAIL-023 concurrent feedback direct-save", () => {
  let remote: string;
  let sha: string;
  let writes: { sha: string; branch: string; content: string }[];
  let raceStatus: number | undefined;

  beforeEach(() => {
    vi.stubEnv("GITHUB_APPLY_REPO", "pds2225/mail");
    vi.stubEnv("GITHUB_APPLY_BRANCH", "main");
    remote = encode([original]);
    sha = "snapshot-a";
    writes = [];
    raceStatus = undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input);
      expect(url.origin).toBe("https://api.github.com");
      expect(url.pathname).toBe(path);
      if (!init?.method) {
        expect(url.searchParams.get("ref")).toBe("main");
        expect(init?.cache).toBe("no-store");
        return Response.json({ sha, content: Buffer.from(remote).toString("base64") });
      }
      expect(init.method).toBe("PUT");
      const body = JSON.parse(String(init.body));
      writes.push(body);
      if (raceStatus) {
        // Writer B appends after A reads, before A's compare-and-swap.
        remote = encode([original, concurrent]);
        sha = "snapshot-b";
        const status = raceStatus;
        raceStatus = undefined;
        return Response.json({ message: "SHA changed" }, { status });
      }
      if (body.sha !== sha) return Response.json({ message: "stale SHA" }, { status: 409 });
      remote = Buffer.from(body.content, "base64").toString("utf-8");
      sha = "saved";
      return Response.json({ commit: { sha, html_url: "https://example.test/commit/saved" } });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("preserves B's appended row when A saves a selection from an older page", async () => {
    remote = encode([original, concurrent]);
    sha = "snapshot-b";
    const response = await POST(selection());
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ applied: true, saveState: "SAVED" });
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({ sha: "snapshot-b", branch: "main" });
    const rows = remote.trim().split("\n").map((line) => JSON.parse(line));
    expect(rows).toHaveLength(2);
    expect(rows.find((row) => row.id === "notice-b")).toEqual(concurrent);
    expect(rows.find((row) => row.id === "notice-a")).toMatchObject({
      ...original, verdict: "O", title: "Selected",
    });
  });

  it.each([409, 422])("fails closed on GitHub %s, then a fresh retry preserves B's row", async (status) => {
    raceStatus = status;
    const response = await POST(selection());
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ ok: false, applied: false, saveState: "CONFLICT" });
    expect(writes).toHaveLength(1); // No blind retry using the stale full-file snapshot.
    expect(writes[0].sha).toBe("snapshot-a");
    expect(remote).toBe(encode([original, concurrent]));

    const retry = await POST(selection());
    expect(retry.status).toBe(200);
    expect(await retry.json()).toMatchObject({ applied: true, saveState: "SAVED" });
    expect(writes).toHaveLength(2);
    expect(writes[1].sha).toBe("snapshot-b");
    const rows = remote.trim().split("\n").map((line) => JSON.parse(line));
    expect(rows).toHaveLength(2);
    expect(rows.find((row) => row.id === "notice-b")).toEqual(concurrent);
    expect(rows.find((row) => row.id === "notice-a").verdict).toBe("O");
  });
});
