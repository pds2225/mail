import { NextResponse } from "next/server";
import { loadGroups, loadSettings, loadSites } from "@/lib/config-loader";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sites = loadSites();
    const groups = loadGroups();
    const settings = loadSettings();
    return NextResponse.json({
      ok: true,
      source: "github_repo_files",
      counts: { sites: sites.length, groups: groups.length },
      sites,
      groups,
      settings: {
        ...settings,
        raw_all_recipients: Array.isArray(settings.raw_all_recipients)
          ? (settings.raw_all_recipients as string[]).map((e) =>
              typeof e === "string" && e.includes("@")
                ? e.replace(/^(.{2})[^@]*(@.*)$/, "$1***$2")
                : e,
            )
          : settings.raw_all_recipients,
      },
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : "config load failed" },
      { status: 500 },
    );
  }
}
