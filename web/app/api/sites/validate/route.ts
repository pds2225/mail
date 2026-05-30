import { NextResponse } from "next/server";
import { loadSites } from "@/lib/config-loader";
import type { SiteAddInput } from "@/lib/site-types";
import { probeUrlReachable, validateSiteInput } from "@/lib/site-validation";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as SiteAddInput & { probeUrl?: boolean };
    const existing = loadSites();
    const validation = validateSiteInput(body, existing);

    let urlReachable: boolean | null = null;
    if (body.probeUrl && validation.normalized.url && validation.ok) {
      urlReachable = await probeUrlReachable(validation.normalized.url);
      if (!urlReachable) {
        validation.warnings.push({
          field: "url",
          level: "warning",
          message: "URL HEAD/GET 접근 실패 (Cloud VM TLS/방화벽 가능)",
        });
      }
    }

    return NextResponse.json({
      ok: validation.ok,
      validation,
      urlReachable,
      existingCount: existing.length,
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : "validate failed" },
      { status: 400 },
    );
  }
}
