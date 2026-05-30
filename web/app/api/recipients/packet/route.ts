import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { buildRecipientPacket } from "@/lib/packet-markdown";
import { repoRoot } from "@/lib/paths";
import { validateRecipients } from "@/lib/recipient-validation";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = (await req.json()) as {
    emails?: string[];
    target?: "group" | "raw_all";
    groupId?: string;
    groupName?: string;
  };
  const validation = validateRecipients(body.emails || []);
  const markdown = buildRecipientPacket({
    target: body.target || "raw_all",
    groupId: body.groupId,
    groupName: body.groupName,
    added: body.emails || [],
    validation,
  });

  const worksPath = path.join(repoRoot(), "WORKS", "RECIPIENT_UPDATE_PACKET.md");
  fs.mkdirSync(path.dirname(worksPath), { recursive: true });
  fs.writeFileSync(worksPath, markdown, "utf-8");

  return NextResponse.json({
    ok: true,
    validation,
    packetPath: "WORKS/RECIPIENT_UPDATE_PACKET.md",
    packetMarkdown: markdown,
    notice: "groups.json / settings.json 은 변경하지 않았습니다.",
  });
}
