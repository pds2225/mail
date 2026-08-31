import { NextResponse } from "next/server";
import { applyAuthError } from "@/lib/apply-auth";
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

export async function POST(req: Request) {
  const authError = applyAuthError(req);
  if (authError) {
    return NextResponse.json({ ok: false, error: authError }, { status: 401 });
  }

  try {
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
      const next = replaceSite(existing, original.id, site);
      const urlReachable =
        body.probeUrl && site.url ? await probeUrlReachable(site.url) : null;
      const written = await putRepoTextFile({
        filePath: "config/sites.json",
        text: serializeSitesJson(next),
        sha: remote.sha,
        message: `chore(sites): update ${site.id} via Vercel admin`,
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
    const next = buildSitesPatch(existing, site);
    const written = await putRepoTextFile({
      filePath: "config/sites.json",
      text: serializeSitesJson(next),
      sha: remote.sha,
      message: `feat(sites): add ${site.id} via Vercel admin`,
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
