import { NextResponse } from "next/server";
import { validateRecipients } from "@/lib/recipient-validation";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = (await req.json()) as { emails?: string[] };
  const validation = validateRecipients(body.emails || []);
  return NextResponse.json({ ok: validation.rejected.length === 0, validation });
}
