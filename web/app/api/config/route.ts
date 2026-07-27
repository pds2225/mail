import { NextResponse } from "next/server";
import { loadGroups, loadSettings, loadSites } from "@/lib/config-loader";
import { maskEmail, publicRecipientEntries } from "@/lib/recipient-validation";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sites = loadSites();
    const groups = loadGroups();
    const settings = loadSettings();
    const safeGroups = groups.map((group) => ({
      ...group,
      recipients: Array.isArray(group.recipients)
        ? group.recipients.map((email) => maskEmail(email))
        : [],
    }));
    const recipientTargets = [
      {
        kind: "raw_all",
        id: "raw_all",
        name: "전체 원문 수신자",
        recipients: publicRecipientEntries(settings.raw_all_recipients),
      },
      ...groups.map((group) => ({
        kind: "group",
        id: group.id,
        name: group.name,
        active: group.active !== false,
        recipients: publicRecipientEntries(group.recipients),
      })),
    ];
    return NextResponse.json({
      ok: true,
      source: "github_repo_files",
      counts: { sites: sites.length, groups: groups.length },
      sites,
      groups: safeGroups,
      recipientTargets,
      settings: {
        ...settings,
        raw_all_recipients: Array.isArray(settings.raw_all_recipients)
          ? (settings.raw_all_recipients as string[]).map((email) => maskEmail(email))
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
