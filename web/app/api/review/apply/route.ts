import { NextResponse } from "next/server";
import { applyAuthError, githubApplyToken } from "@/lib/apply-auth";
import { pendingConfigCommitUrl, type PendingConfigApply } from "@/lib/github-commit-url";
import { getRepoTextFile, githubBranch, putRepoTextFile } from "@/lib/github-apply";

export const dynamic = "force-dynamic";

function upsertFeedback(
  text: string,
  item: { id: string; title: string; verdict: "O" | "X" },
): string {
  const rows = new Map<string, Record<string, unknown>>();
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const row = JSON.parse(line) as Record<string, unknown>;
      const id = String(row.id || "").trim();
      if (id) rows.set(id, row);
    } catch {
      // Preserve valid historical rows; malformed rows are already ignored by the Python reader.
    }
  }
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  const previous = rows.get(item.id) || {};
  rows.set(item.id, {
    ...previous,
    id: item.id,
    verdict: item.verdict,
    tier: "C",
    source: "dashboard-ox",
    title: item.title.slice(0, 110),
    first_seen: previous.first_seen || now,
    last_seen: now,
  });
  return `${[...rows.keys()]
    .sort()
    .map((id) => JSON.stringify(rows.get(id)))
    .join("\n")}\n`;
}

export async function POST(req: Request) {
  const authError = applyAuthError(req);
  if (authError) return NextResponse.json({ ok: false, error: authError }, { status: 401 });

  try {
    const body = (await req.json()) as Record<string, unknown>;
    const id = String(body.id || "").trim();
    const title = String(body.title || "").trim();
    const verdict = String(body.verdict || "").trim().toUpperCase();
    if (!/^[A-Za-z0-9_.:\-%]{1,120}$/.test(id)) {
      return NextResponse.json({ ok: false, error: "공고 ID 형식이 올바르지 않습니다." }, { status: 400 });
    }
    if (verdict !== "O" && verdict !== "X") {
      return NextResponse.json({ ok: false, error: "O 또는 X만 선택할 수 있습니다." }, { status: 400 });
    }

    const item = { id, title, verdict: verdict as "O" | "X" };
    const token = githubApplyToken(req);
    const pending: PendingConfigApply = { v: 1, resource: "review", item };
    if (!token) {
      return NextResponse.json({
        ok: true,
        applied: false,
        githubCommitUrl: pendingConfigCommitUrl(pending),
        notice: "검수 저장 확인 화면이 열립니다. Commit changes를 누르면 O/X가 기록됩니다.",
      });
    }

    const remote = await getRepoTextFile("data/golden/feedback_labels.jsonl", token);
    const written = await putRepoTextFile({
      filePath: "data/golden/feedback_labels.jsonl",
      text: upsertFeedback(remote.text, item),
      sha: remote.sha,
      message: `chore(review): ${item.verdict} ${item.id} via admin web`,
      token,
    });
    return NextResponse.json({
      ok: true,
      applied: true,
      branch: githubBranch(),
      commitUrl: written.commitUrl,
      verdict: item.verdict,
      notice: "O/X 검수를 저장했습니다.",
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "review apply failed" },
      { status: 500 },
    );
  }
}
