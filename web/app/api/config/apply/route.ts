import { NextResponse } from "next/server";
import { applyAuthError, githubApplyToken } from "@/lib/apply-auth";
import {
  pendingConfigManualCommitUrl,
  serializePendingApply,
  type PendingConfigApply,
} from "@/lib/github-commit-url";
import {
  getRepoTextFile,
  githubBranch,
  putRepoTextFile,
  repoTextFileExists,
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

async function githubWebApply(pending: PendingConfigApply) {
  const pendingFileExists = await repoTextFileExists(".apply/config-pending.json");
  return {
    ok: true,
    applied: false,
    manualPasteRequired: true,
    pendingFileExists,
    githubCommitUrl: pendingConfigManualCommitUrl({ existing: pendingFileExists }),
    pendingFilename: "config-pending.json",
    pendingContent: serializePendingApply(pending),
    notice:
      "저장 데이터를 복사한 뒤 GitHub 저장 화면에 붙여넣고 Commit changes를 누르면 설정이 반영됩니다.",
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

      const remote = await getRepoTextFile("config/groups.json");
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
      const pending: PendingConfigApply = { v: 1, resource: "group", id, patch };
      if (!token) return NextResponse.json(await githubWebApply(pending));

      const written = await putRepoTextFile({
        filePath: "config/groups.json",
        text: `${JSON.stringify(next, null, 2)}\n`,
        sha: remote.sha,
        message: `chore(groups): update ${id} via admin web`,
        token,
      });
      return NextResponse.json({
        ok: true,
        applied: true,
        branch: githubBranch(),
        commitUrl: written.commitUrl,
        notice: "그룹 설정을 저장했습니다.",
      });
    }

    if (resource === "settings") {
      const patch = pickPatch(body.patch, SETTINGS_FIELDS);
      if (!Object.keys(patch).length) {
        return NextResponse.json({ ok: false, error: "변경할 설정 값이 없습니다." }, { status: 400 });
      }
      const remote = await getRepoTextFile("config/settings.json");
      const parsed = JSON.parse(remote.text) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("config/settings.json 형식이 객체가 아닙니다.");
      }
      const next = { ...(parsed as Record<string, unknown>), ...patch };
      const pending: PendingConfigApply = { v: 1, resource: "settings", patch };
      if (!token) return NextResponse.json(await githubWebApply(pending));

      const written = await putRepoTextFile({
        filePath: "config/settings.json",
        text: `${JSON.stringify(next, null, 2)}\n`,
        sha: remote.sha,
        message: "chore(settings): update via admin web",
        token,
      });
      return NextResponse.json({
        ok: true,
        applied: true,
        branch: githubBranch(),
        commitUrl: written.commitUrl,
        notice: "메일링 설정을 저장했습니다.",
      });
    }

    return NextResponse.json({ ok: false, error: "지원하지 않는 저장 대상입니다." }, { status: 400 });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "apply failed" },
      { status: 500 },
    );
  }
}
