import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { buildRecipientPacket } from "@/lib/packet-markdown";
import { loadGroups, loadSettings } from "@/lib/config-loader";
import { repoRoot } from "@/lib/paths";
import {
  maskEmail,
  planRecipientUpdate,
  publicRecipientValidation,
} from "@/lib/recipient-validation";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as {
      emails?: string[];
      addEmails?: string[];
      removeRecipientIds?: string[];
      target?: "group" | "raw_all";
      groupId?: string;
    };
    const target = body.target || "raw_all";
    const groups = loadGroups();
    const settings = loadSettings();
    const group = target === "group" ? groups.find((item) => item.id === body.groupId) : undefined;

    if (target === "group" && !group) {
      return NextResponse.json(
        { ok: false, error: "수신자 그룹을 찾을 수 없습니다." },
        { status: 400 },
      );
    }

    const existing =
      target === "group" ? group?.recipients : settings.raw_all_recipients;
    const plan = planRecipientUpdate(
      existing,
      body.addEmails || body.emails || [],
      body.removeRecipientIds || [],
    );
    const validation = {
      valid: plan.added,
      rejected: plan.rejected,
      masked: plan.added.map(maskEmail),
    };

    if (!plan.ok) {
      return NextResponse.json(
        {
          ok: false,
          validation: publicRecipientValidation(validation),
          update: {
            beforeCount: plan.beforeCount,
            afterCount: plan.afterCount,
            addedMasked: plan.added.map(maskEmail),
            removedMasked: plan.removed.map(maskEmail),
          },
        },
        { status: 400 },
      );
    }

    const markdown = buildRecipientPacket({
      target,
      groupId: group?.id,
      groupName: group?.name,
      added: plan.added,
      removed: plan.removed,
      beforeCount: plan.beforeCount,
      afterCount: plan.afterCount,
      validation,
    });

    let packetPath: string | null = null;
    try {
      const worksPath = path.join(repoRoot(), "WORKS", "RECIPIENT_UPDATE_PACKET.md");
      fs.mkdirSync(path.dirname(worksPath), { recursive: true });
      fs.writeFileSync(worksPath, markdown, "utf-8");
      packetPath = "WORKS/RECIPIENT_UPDATE_PACKET.md";
    } catch {
      // Vercel serverless에서는 파일시스템이 읽기 전용일 수 있어 응답 본문만 사용한다.
    }

    return NextResponse.json({
      ok: true,
      validation: publicRecipientValidation(validation),
      update: {
        beforeCount: plan.beforeCount,
        afterCount: plan.afterCount,
        addedMasked: plan.added.map(maskEmail),
        removedMasked: plan.removed.map(maskEmail),
      },
      packetPath,
      packetMarkdown: markdown,
      notice: "config/groups.json / config/settings.json은 변경하지 않았습니다.",
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "recipient packet failed" },
      { status: 500 },
    );
  }
}
