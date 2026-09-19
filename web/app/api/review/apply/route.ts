import { NextResponse } from "next/server";
import { applyAuthError, githubApplyToken } from "@/lib/apply-auth";
import { githubEditFileUrl } from "@/lib/github-commit-url";
import { getRepoTextFile, githubBranch, putRepoTextFile } from "@/lib/github-apply";

export const dynamic = "force-dynamic";

type ReviewVerdictInput = { id: string; title: string; verdict: "O" | "X" };


function parseItem(raw: unknown): ReviewVerdictInput | null {
  if (!raw || typeof raw !== "object") return null;
  const body = raw as Record<string, unknown>;
  const id = String(body.id || "").trim();
  const title = String(body.title || "").trim();
  const verdict = String(body.verdict || "").trim().toUpperCase();
  if (!/^[A-Za-z0-9_.:\-%]{1,120}$/.test(id)) return null;
  if (verdict !== "O" && verdict !== "X") return null;
  return { id, title, verdict: verdict as "O" | "X" };
}

function upsertFeedback(text: string, items: ReviewVerdictInput[]): string {
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
  for (const item of items) {
    const previous = rows.get(item.id) || {};
    rows.set(item.id, {
      ...previous,
      id: item.id,
      verdict: item.verdict,
      tier: "C",
      source: "dashboard-ox",
      title: item.title.slice(0, 110) || String(previous.title || ""),
      first_seen: previous.first_seen || now,
      last_seen: now,
    });
  }
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
    // 단일 {id,title,verdict}와 배치 {items:[...]} 둘 다 받는다(하위호환).
    const rawItems = Array.isArray(body.items) ? body.items : [body];
    const items = rawItems.map(parseItem).filter((item): item is ReviewVerdictInput => item !== null);
    if (items.length === 0) {
      return NextResponse.json(
        { ok: false, error: "공고 ID 또는 O/X 값이 올바르지 않습니다." },
        { status: 400 },
      );
    }

    const token = githubApplyToken(req);
    const feedbackPath = "data/golden/feedback_labels.jsonl";
    if (!token) {
      const remote = await getRepoTextFile(feedbackPath);
      return NextResponse.json({
        ok: true,
        applied: false,
        manualPasteRequired: true,
        manualFilePath: feedbackPath,
        manualContent: upsertFeedback(remote.text, items),
        githubCommitUrl: githubEditFileUrl(feedbackPath),
        notice:
          `검수 ${items.length}건을 최종 검수 파일에 저장하려면 아래 내용을 복사해 GitHub 파일 전체를 교체한 뒤 Commit changes를 누르세요.`,
      });
    }

    const remote = await getRepoTextFile(feedbackPath, token);
    const summary = items.length === 1 ? `${items[0].verdict} ${items[0].id}` : `${items.length}건`;
    const written = await putRepoTextFile({
      filePath: feedbackPath,
      text: upsertFeedback(remote.text, items),
      sha: remote.sha,
      message: `chore(review): ${summary} via admin web`,
      token,
    });
    return NextResponse.json({
      ok: true,
      applied: true,
      branch: githubBranch(),
      commitUrl: written.commitUrl,
      items,
      notice: `O/X 검수 ${items.length}건을 저장했습니다.`,
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "review apply failed" },
      { status: 500 },
    );
  }
}
