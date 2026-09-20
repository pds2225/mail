import { NextResponse } from "next/server";
import { applyAuthError, githubApplyToken } from "@/lib/apply-auth";
import { githubEditFileUrl } from "@/lib/github-commit-url";
import {
  getRepoBranchHead,
  getRepoTextFile,
  githubBranch,
  putRepoTextFile,
} from "@/lib/github-apply";

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

function isConflict(error: unknown): boolean {
  return error instanceof Error && error.name === "GithubFileConflictError";
}

export async function POST(req: Request) {
  const authError = applyAuthError(req);
  if (authError) return NextResponse.json({ ok: false, error: authError }, { status: 401 });

  try {
    const body = (await req.json()) as Record<string, unknown>;
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
      const sourceCommitSha = await getRepoBranchHead();
      const remote = await getRepoTextFile(feedbackPath, "", sourceCommitSha);
      return NextResponse.json({
        ok: true,
        applied: false,
        saveState: "PR_PENDING",
        manualPasteRequired: true,
        manualFilePath: feedbackPath,
        manualContent: upsertFeedback(remote.text, items),
        sourceBlobSha: remote.sha,
        sourceCommitSha,
        githubCommitUrl: githubEditFileUrl(feedbackPath, { branch: sourceCommitSha }),
        notice:
          `검수 ${items.length}건은 아직 저장 완료가 아닙니다. 기준 커밋에서 편집한 뒤 Propose changes → Create pull request → Checks → merge까지 완료하세요.`,
      });
    }

    const remote = await getRepoTextFile(feedbackPath, token);
    const summary = items.length === 1 ? `${items[0].verdict} ${items[0].id}` : `${items.length}건`;
    try {
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
        saveState: "SAVED",
        branch: githubBranch(),
        commitUrl: written.commitUrl,
        items,
        notice: `O/X 검수 ${items.length}건을 저장했습니다.`,
      });
    } catch (error) {
      if (isConflict(error)) {
        return NextResponse.json(
          {
            ok: false,
            applied: false,
            saveState: "CONFLICT",
            error: error instanceof Error ? error.message : "원격 파일 충돌",
          },
          { status: 409 },
        );
      }
      throw error;
    }
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        applied: false,
        saveState: "FAILED",
        error: error instanceof Error ? error.message : "review apply failed",
      },
      { status: 500 },
    );
  }
}
