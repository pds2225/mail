import { NextResponse } from "next/server";
import { applyStatus } from "@/lib/apply-auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const status = applyStatus();
  return NextResponse.json({
    ok: true,
    ...status,
  });
}
