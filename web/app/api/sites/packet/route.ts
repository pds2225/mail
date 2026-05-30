import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { loadSites } from "@/lib/config-loader";
import { buildSiteAddPacket } from "@/lib/packet-markdown";
import { buildSitesPatch } from "@/lib/site-patch";
import { repoRoot } from "@/lib/paths";
import type { SiteAddInput } from "@/lib/site-types";
import { probeUrlReachable, validateSiteInput } from "@/lib/site-validation";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as SiteAddInput & { probeUrl?: boolean };
    const existing = loadSites();
    const validation = validateSiteInput(body, existing);
    if (!validation.ok) {
      return NextResponse.json({ ok: false, validation }, { status: 400 });
    }

    const site = validation.normalized as import("@/lib/site-types").SiteRecord;
    const urlReachable =
      body.probeUrl && site.url ? await probeUrlReachable(site.url) : null;

    const branch = `feat/site-add-${site.id}`;
    const markdown = buildSiteAddPacket({
      branch,
      site,
      validation,
      existingCount: existing.length,
      urlReachable,
    });

    const nextSites = buildSitesPatch(existing, site);
    const writtenPaths: string[] = [];
    try {
      const worksDir = path.join(repoRoot(), "WORKS");
      fs.mkdirSync(worksDir, { recursive: true });
      fs.writeFileSync(path.join(worksDir, "SITE_ADD_PR_PACKET.md"), markdown, "utf-8");
      writtenPaths.push("WORKS/SITE_ADD_PR_PACKET.md");
      const docsPath = path.join(repoRoot(), "docs", "SITE_ADD_PR_PACKET.md");
      fs.mkdirSync(path.dirname(docsPath), { recursive: true });
      fs.writeFileSync(docsPath, markdown, "utf-8");
      writtenPaths.push("docs/SITE_ADD_PR_PACKET.md");
    } catch {
      /* Vercel serverless 등 읽기 전용 FS — 응답 본문만 사용 */
    }

    return NextResponse.json({
      ok: true,
      branch,
      site,
      validation,
      urlReachable,
      sitesJsonPreview: nextSites.slice(-3),
      packetPaths: writtenPaths,
      packetMarkdown: markdown,
      prTitle: `feat(sites): add ${site.id} — ${site.name}`,
      notice: "운영 sites.json 은 변경하지 않았습니다. PR 승인 후 반영하세요.",
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : "packet failed" },
      { status: 500 },
    );
  }
}
