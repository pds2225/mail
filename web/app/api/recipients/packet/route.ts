import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { loadGroups, loadSettings } from "@/lib/config-loader";
import { buildRecipientPacket } from "@/lib/packet-markdown";
import { repoRoot } from "@/lib/paths";
import {
  buildGroupRecipientsAppendPatch,
  buildRawAllRecipientsAppendPatch,
  type GroupRecord,
} from "@/lib/recipient-patch";
import { validateRecipients } from "@/lib/recipient-validation";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as {
      emails?: string[];
      target?: "group" | "raw_all";
      groupId?: string;
    };
    const validation = validateRecipients(body.emails || []);
    if (validation.valid.length === 0) {
      return NextResponse.json(
        { ok: false, validation, error: "유효한 이메일이 없습니다." },
        { status: 400 },
      );
    }
    if (validation.rejected.length > 0) {
      return NextResponse.json(
        {
          ok: false,
          validation,
          error: "거부된 항목이 있습니다. 수정 후 다시 시도하세요.",
        },
        { status: 400 },
      );
    }

    const target = body.target || "raw_all";
    let groupName: string | undefined;
    let patchSnippet: string;

    if (target === "group") {
      const groups = loadGroups() as GroupRecord[];
      const group = groups.find((g) => g.id === body.groupId);
      if (!group) {
        return NextResponse.json({ ok: false, error: "그룹을 찾을 수 없습니다." }, { status: 400 });
      }
      groupName = group.name;
      patchSnippet = buildGroupRecipientsAppendPatch(group, validation.valid);
    } else {
      loadSettings();
      patchSnippet = buildRawAllRecipientsAppendPatch(validation.valid);
    }

    const markdown = buildRecipientPacket({
      target,
      groupId: body.groupId,
      groupName,
      addedValid: validation.valid,
      validation,
      patchSnippet,
    });

    const writtenPaths: string[] = [];
    try {
      const worksDir = path.join(repoRoot(), "WORKS");
      fs.mkdirSync(worksDir, { recursive: true });
      const worksPath = path.join(worksDir, "RECIPIENT_UPDATE_PACKET.md");
      fs.writeFileSync(worksPath, markdown, "utf-8");
      writtenPaths.push("WORKS/RECIPIENT_UPDATE_PACKET.md");
    } catch {
      /* read-only FS on Vercel */
    }

    return NextResponse.json({
      ok: true,
      validation: {
        validCount: validation.valid.length,
        masked: validation.masked,
        rejected: validation.rejected.map((r) => ({ reason: r.reason })),
      },
      target,
      groupId: body.groupId,
      patchSnippet,
      packetPaths: writtenPaths,
      packetMarkdown: markdown,
      notice: "groups.json / settings.json 은 변경하지 않았습니다. PR 승인 후 반영하세요.",
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : "packet failed" },
      { status: 500 },
    );
  }
}
