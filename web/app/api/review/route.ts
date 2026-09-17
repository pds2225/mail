import { NextResponse } from "next/server";
import { getRepoTextFile } from "@/lib/github-apply";

export const dynamic = "force-dynamic";

type QueueItem = { id: string; title: string };

function feedbackMap(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const row = JSON.parse(line) as Record<string, unknown>;
      const id = String(row.id || "").trim();
      const verdict = String(row.verdict || "").trim().toUpperCase();
      if (id && (verdict === "O" || verdict === "X")) out[id] = verdict;
    } catch {
      // Ignore malformed historic lines; the Python accuracy pipeline does the same.
    }
  }
  return out;
}

export async function GET() {
  try {
    const [queueFile, labelsFile] = await Promise.all([
      getRepoTextFile("data/golden/ox_title_queue.json"),
      getRepoTextFile("data/golden/feedback_labels.jsonl"),
    ]);
    const queue = JSON.parse(queueFile.text) as { items?: QueueItem[]; count?: number };
    const labels = feedbackMap(labelsFile.text);
    const items = (queue.items || []).map((item) => ({
      id: item.id,
      title: item.title,
      verdict: labels[item.id] || null,
    }));
    return NextResponse.json({ ok: true, count: items.length, items });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "review load failed" },
      { status: 500 },
    );
  }
}
