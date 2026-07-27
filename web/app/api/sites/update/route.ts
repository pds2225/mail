import fs from "fs";
import path from "path";
import { NextResponse } from "next/server";
import { loadSites } from "@/lib/config-loader";
import { buildSiteUpdatePacket } from "@/lib/packet-markdown";
import { repoRoot } from "@/lib/paths";
import { changedSiteFields, replaceSite } from "@/lib/site-patch";
import type { SiteEditInput, SiteRecord } from "@/lib/site-types";
import { probeUrlReachable, validateSiteEditInput } from "@/lib/site-validation";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as SiteEditInput & {
      createPacket?: boolean;
      probeUrl?: boolean;
    };
    const existing = loadSites();
    const original = existing.find((site) => site.id === body.id);
    const validation = validateSiteEditInput(body, existing);

    if (!validation.ok || !original) {
      return NextResponse.json({ ok: false, validation }, { status: 400 });
    }

    const site = validation.normalized as SiteRecord;
    const urlReachable =
      body.probeUrl && site.url ? await probeUrlReachable(site.url) : null;
    const fields = changedSiteFields(original, site);

    if (!body.createPacket) {
      return NextResponse.json({
        ok: true,
        validation: {
          ...validation,
          checks: { ...validation.checks, urlReachable },
        },
        changedFields: fields,
      });
    }

    const branch = `chore/site-update-${site.id}`;
    const markdown = buildSiteUpdatePacket({
      branch,
      before: original,
      after: site,
      validation,
      urlReachable,
    });
    const packetPaths: string[] = [];
    try {
      const worksPath = path.join(repoRoot(), "WORKS", "SITE_UPDATE_PR_PACKET.md");
      fs.mkdirSync(path.dirname(worksPath), { recursive: true });
      fs.writeFileSync(worksPath, markdown, "utf-8");
      packetPaths.push("WORKS/SITE_UPDATE_PR_PACKET.md");
    } catch {
      // Vercel serverless에서는 파일시스템이 읽기 전용일 수 있어 응답 본문만 사용한다.
    }

    return NextResponse.json({
      ok: true,
      branch,
      site,
      validation: {
        ...validation,
        checks: { ...validation.checks, urlReachable },
      },
      changedFields: fields,
      sitesJsonPreview: replaceSite(existing, original.id, site).filter(
        (entry) => entry.id === site.id,
      ),
      packetPaths,
      packetMarkdown: markdown,
      prTitle: `chore(sites): update ${site.id} — ${site.name}`,
      notice: "운영 config/sites.json은 변경하지 않았습니다. PR 승인 후 반영하세요.",
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "site update failed" },
      { status: 500 },
    );
  }
}
