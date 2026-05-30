import { NextResponse } from "next/server";
import { loadGroups, loadSettings, loadSites } from "@/lib/config-loader";
import { maskGroupsForApi, maskSettingsForApi } from "@/lib/config-mask";
import { configSourceLabel } from "@/lib/paths";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sites = loadSites();
    const groups = loadGroups();
    const settings = loadSettings();
    return NextResponse.json({
      ok: true,
      source: configSourceLabel() === "bundled" ? "github_repo_files_bundled" : "github_repo_files",
      counts: { sites: sites.length, groups: (groups as unknown[]).length },
      sites,
      groups: maskGroupsForApi(groups as unknown[]),
      settings: maskSettingsForApi(settings),
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : "config load failed" },
      { status: 500 },
    );
  }
}
