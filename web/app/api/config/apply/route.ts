import { NextResponse } from "next/server";
import { applyAuthError, githubApplyToken } from "@/lib/apply-auth";
import { githubEditFileUrl } from "@/lib/github-commit-url";
import {
  getRepoBranchHead,
  getRepoTextFile,
  githubBranch,
  putRepoTextFile,
  type RepoFile,
} from "@/lib/github-apply";

export const dynamic = "force-dynamic";

const GROUP_FIELDS = new Set([
  "name",
  "active",
  "required_conditions",
  "or_keywords",
  "and_keyword_groups",
  "exclude_keywords",
  "support_types",
]);

const SETTINGS_FIELDS = new Set([
  "date_filter_enabled",
  "days_back",
  "raw_all_enabled",
  "date_unknown_policy",
  "date_unknown_max_age_days",
  "region_unknown_mail_limit",
]);

function pickPatch(input: unknown, allowed: Set<string>): Record<string, unknown> {
  if (!input || typeof input !== "object" || Array.isArray(input)) return {};
  return Object.fromEntries(
    Object.entries(input as Record<string, unknown>).filter(([key]) => allowed.has(key)),
  );
}

function githubWebApply(
  filePath: string,
  content: string,
  remote: RepoFile,
  sourceCommitSha: string,
) {
  return {
    ok: true,
    applied: false,
    saveState: "PR_PENDING",
    manualPasteRequired: true,
    manualFilePath: filePath,
    manualContent: content,
    sourceBlobSha: remote.sha,
    sourceCommitSha,
    githubCommitUrl: githubEditFileUrl(filePath, { branch: sourceCommitSha }),
    notice:
      "아직 저장 완료가 아닙니다. 기준 커밋에서 편집한 뒤 Propose changes → Create pull request → Checks → merge까지 완료하세요.",
  };
}

function isConflict(error: unknown): boolean {
  return error instanceof Error && error.name === "GithubFileConflictError";
}

async function loadForApply(filePath: string, token: string): Promise<{
  remote: RepoFile;
  sourceCommitSha?: string;
}> {
  if (token) {
    return { remote: await getRepoTextFile(filePath, token) };
  }
  const sourceCommitSha = await getRepoBranchHead();
  return {
    sourceCommitSha,
    remote: await getRepoTextFile(filePath, "", sourceCommitSha),
  };
}

export async function POST(req: Request) {
  const authError = applyAuthError(req);
  if (authError) {
    return NextResponse.json({ ok: false, error: authError }, { status: 401 });
  }

  try {
    const body = (await req.json()) as Record<string, unknown>;
    const resource = String(body.resource || "");
    const token = githubApplyToken(req);

    if (resource === "group") {
      const id = String(body.id || "").trim();
      const patch = pickPatch(body.patch, GROUP_FIELDS);
      if (!id) return NextResponse.json({ ok: false, error: "그룹 ID가 없습니다." }, { status: 400 });
      if (!Object.keys(patch).length) {
        return NextResponse.json({ ok: false, error: "변경할 그룹 값이 없습니다." }, { status: 400 });
      }

      const filePath = "config/groups.json";
      const { remote, sourceCommitSha } = await loadForApply(filePath, token);
      const parsed = JSON.parse(remote.text) as unknown;
      if (!Array.isArray(parsed)) throw new Error("config/groups.json 형식이 배열이 아닙니다.");
      const index = parsed.findIndex(
        (item) => item && typeof item === "object" && String((item as Record<string, unknown>).id) === id,
      );
      if (index < 0) return NextResponse.json({ ok: false, error: "그룹을 찾지 못했습니다." }, { status: 404 });

      const current = parsed[index] as Record<string, unknown>;
      const nextGroup = { ...current, ...patch };
      const next = [...parsed];
      next[index] = nextGroup;
      const nextText = `${JSON.stringify(next, null, 2)}\n`;

      if (!token && sourceCommitSha) {
        return NextResponse.json(githubWebApply(filePath, nextText, remote, sourceCommitSha));
      }

      try {
        const written = await putRepoTextFile({
          filePath,
          text: nextText,
          sha: remote.sha,
          message: `chore(groups): update ${id} via admin web`,
          token,
        });
        return NextResponse.json({
          ok: true,
          applied: true,
          saveState: "SAVED",
          branch: githubBranch(),
          commitUrl: written.commitUrl,
          notice: "그룹 설정을 저장했습니다.",
        });
      } catch (error) {
        if (isConflict(error)) {
          return NextResponse.json(
            { ok: false, applied: false, saveState: "CONFLICT", error: (error as Error).message },
            { status: 409 },
          );
        }
        throw error;
      }
    }

    if (resource === "settings") {
      const patch = pickPatch(body.patch, SETTINGS_FIELDS);
      if (!Object.keys(patch).length) {
        return NextResponse.json({ ok: false, error: "변경할 설정 값이 없습니다." }, { status: 400 });
      }
      const filePath = "config/settings.json";
      const { remote, sourceCommitSha } = await loadForApply(filePath, token);
      const parsed = JSON.parse(remote.text) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("config/settings.json 형식이 객체가 아닙니다.");
      }
      const next = { ...(parsed as Record<string, unknown>), ...patch };
      const nextText = `${JSON.stringify(next, null, 2)}\n`;

      if (!token && sourceCommitSha) {
        return NextResponse.json(githubWebApply(filePath, nextText, remote, sourceCommitSha));
      }

      try {
        const written = await putRepoTextFile({
          filePath,
          text: nextText,
          sha: remote.sha,
          message: "chore(settings): update via admin web",
          token,
        });
        return NextResponse.json({
          ok: true,
          applied: true,
          saveState: "SAVED",
          branch: githubBranch(),
          commitUrl: written.commitUrl,
          notice: "메일링 설정을 저장했습니다.",
        });
      } catch (error) {
        if (isConflict(error)) {
          return NextResponse.json(
            { ok: false, applied: false, saveState: "CONFLICT", error: (error as Error).message },
            { status: 409 },
          );
        }
        throw error;
      }
    }

    return NextResponse.json({ ok: false, error: "지원하지 않는 저장 대상입니다." }, { status: 400 });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        applied: false,
        saveState: "FAILED",
        error: error instanceof Error ? error.message : "apply failed",
      },
      { status: 500 },
    );
  }
}
