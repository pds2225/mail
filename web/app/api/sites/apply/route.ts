import { NextResponse } from "next/server";
import { applyAuthError, githubApplyToken } from "@/lib/apply-auth";
import { pendingApplyCommitUrl } from "@/lib/github-commit-url";
import {
  getRepoTextFile,
  githubBranch,
  parseSitesJson,
  putRepoTextFile,
  serializeSitesJson,
} from "@/lib/github-apply";
import { buildSitesPatch, changedSiteFields, replaceSite } from "@/lib/site-patch";
import type { SiteAddInput, SiteEditInput, SiteRecord } from "@/lib/site-types";
import { probeUrlReachable, validateSiteEditInput, validateSiteInput } from "@/lib/site-validation";

export const dynamic = "force-dynamic";

type ApplyBody = (SiteAddInput | SiteEditInput) & {
  mode?: "add" | "update";
  probeUrl?: boolean;
};

function githubWebApply(mode: "add" | "update", site: SiteRecord) {
  const githubCommitUrl = pendingApplyCommitUrl({ v: 1, mode, site });
  return {
    ok: true,
    applied: false,
    githubCommitUrl,
    site,
    notice:
      "GitHub 커밋 화면을 열었습니다. 로그인된 저장소 계정으로 Commit changes 를 누르면 1~2분 뒤 목록에 반영됩니다. 토큰은 필요 없습니다.",
  };
}

export async function POST(req: Request) {
  const authError = applyAuthError(req);
  if (authError) {
    return NextResponse.json({ ok: false, error: authError }, { status: 401 });
  }

  try {
    const token = githubApplyToken(req);
    const body = (await req.json()) as ApplyBody;
    const mode = body.mode || ("id" in body && body.id ? "update" : "add");
    const remote = await getRepoTextFile("config/sites.json");
    const existing = parseSitesJson(remote.text);

    if (mode === "update") {
      const edit = body as SiteEditInput;
      const original = existing.find((site) => site.id === edit.id);
      const validation = validateSiteEditInput(edit, existing);
      if (!validation.ok || !original) {
        return NextResponse.json({ ok: false, validation }, { status: 400 });
      }
      const site = validation.normalized as SiteRecord;
      const fields = changedSiteFields(original, site);
      if (!fields.length) {
        return NextResponse.json({
          ok: true,
          applied: false,
          notice: "변경된 필드가 없습니다.",
          site,
          changedFields: [],
        });
      }
      const urlReachable =
        body.probeUrl && site.url ? await probeUrlReachable(site.url) : null;
      if (!token) {
        return NextResponse.json({
          ...githubWebApply("update", site),
          changedFields: fields,
          validation: {
            ...validation,
            checks: { ...validation.checks, urlReachable },
          },
        });
      }
      const next = replaceSite(existing, original.id, site);
      const written = await putRepoTextFile({
        filePath: "config/sites.json",
        text: serializeSitesJson(next),
        sha: remote.sha,
        message: `chore(sites): update ${site.id} via Vercel admin`,
        token,
      });
      return NextResponse.json({
        ok: true,
        applied: true,
        branch: githubBranch(),
        site,
        changedFields: fields,
        validation: {
          ...validation,
          checks: { ...validation.checks, urlReachable },
        },
        commitUrl: written.commitUrl,
        htmlUrl: written.htmlUrl,
        notice: "GitHub main의 config/sites.json 에 반영했습니다. 1~2분 뒤 이 화면에 새 목록이 보입니다.",
      });
    }

    const validation = validateSiteInput(body as SiteAddInput, existing);
    if (!validation.ok) {
      return NextResponse.json({ ok: false, validation }, { status: 400 });
    }
    const site = validation.normalized as SiteRecord;
    const urlReachable =
      body.probeUrl && site.url ? await probeUrlReachable(site.url) : null;
    if (!token) {
      return NextResponse.json({
        ...githubWebApply("add", site),
        validation: {
          ...validation,
          checks: { ...validation.checks, urlReachable },
        },
      });
    }
    const next = buildSitesPatch(existing, site);
    const written = await putRepoTextFile({
      filePath: "config/sites.json",
      text: serializeSitesJson(next),
      sha: remote.sha,
      message: `feat(sites): add ${site.id} via Vercel admin`,
      token,
    });
    return NextResponse.json({
      ok: true,
      applied: true,
      branch: githubBranch(),
      site,
      validation: {
        ...validation,
        checks: { ...validation.checks, urlReachable },
      },
      commitUrl: written.commitUrl,
      htmlUrl: written.htmlUrl,
      notice: "GitHub main의 config/sites.json 에 추가했습니다. 1~2분 뒤 사이트 목록에 나타납니다.",
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "apply failed" },
      { status: 500 },
    );
  }
}
