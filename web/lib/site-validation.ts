import { COLLECTOR_TYPES, type SiteAddInput, type SiteRecord } from "./site-types";

export type ValidationIssue = {
  field: string;
  level: "error" | "warning";
  message: string;
};

export type SiteValidationResult = {
  ok: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  normalized: Partial<SiteRecord> & { id: string };
  checks: {
    collectorRegistered: boolean;
    urlReachable: boolean | null;
    dateUnknownRisk: "낮음" | "중간" | "높음";
    dryRunReady: boolean;
    stableIdNote: string;
  };
};

function slugId(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
  return base || `site_${Date.now()}`;
}

export function normalizeUrl(raw: string): string {
  return raw.trim().replace(/\s+/g, "");
}

export function validateSiteInput(
  input: SiteAddInput,
  existingSites: SiteRecord[],
): SiteValidationResult {
  const errors: ValidationIssue[] = [];
  const warnings: ValidationIssue[] = [];

  const name = (input.name || "").trim();
  const url = normalizeUrl(input.url || "");
  const collectorType = (input.collectorType || "").trim();
  const category = (input.category || "").trim();

  if (!name) {
    errors.push({ field: "name", level: "error", message: "사이트명은 필수입니다." });
  }
  if (!url) {
    errors.push({ field: "url", level: "error", message: "URL은 필수입니다." });
  } else if (!/^https?:\/\//i.test(url)) {
    errors.push({ field: "url", level: "error", message: "URL은 http:// 또는 https:// 로 시작해야 합니다." });
  } else {
    try {
      const u = new URL(url);
      if (!["http:", "https:"].includes(u.protocol)) {
        errors.push({ field: "url", level: "error", message: "http/https 프로토콜만 허용됩니다." });
      }
    } catch {
      errors.push({ field: "url", level: "error", message: "URL 형식이 올바르지 않습니다." });
    }
  }

  if (!collectorType) {
    errors.push({ field: "collectorType", level: "error", message: "수집 방식을 선택하세요." });
  } else if (!COLLECTOR_TYPES.includes(collectorType as (typeof COLLECTOR_TYPES)[number])) {
    errors.push({ field: "collectorType", level: "error", message: "등록되지 않은 수집 방식입니다." });
  }

  const urlLower = url.toLowerCase();
  const dupUrl = existingSites.find((s) => (s.url || "").trim().toLowerCase() === urlLower);
  if (dupUrl) {
    errors.push({
      field: "url",
      level: "error",
      message: `동일 URL이 이미 등록되어 있습니다 (${dupUrl.name}).`,
    });
  }

  const dupName = existingSites.find(
    (s) => s.name.trim().toLowerCase() === name.toLowerCase(),
  );
  if (dupName && name) {
    warnings.push({
      field: "name",
      level: "warning",
      message: `동일한 사이트명이 있습니다 (${dupName.id}).`,
    });
  }

  const dupId = existingSites.find((s) => s.id === (input.suggestedId || slugId(name)));
  let id = input.suggestedId?.trim() || slugId(name);
  if (dupId) {
    id = `${id}_${Date.now().toString(36).slice(-4)}`;
    warnings.push({ field: "id", level: "warning", message: `ID 충돌로 ${id} 를 제안합니다.` });
  }

  const collectorRegistered = COLLECTOR_TYPES.includes(
    collectorType as (typeof COLLECTOR_TYPES)[number],
  );
  const needsSelectors = ["html_table", "html_card"].includes(collectorType);
  if (needsSelectors) {
    warnings.push({
      field: "collectorType",
      level: "warning",
      message: "html_table/html_card는 selectors.row 설정이 PR 반영 시 필요할 수 있습니다.",
    });
  }

  const dateUnknownRisk: "낮음" | "중간" | "높음" =
    collectorType === "bizinfo_api" || collectorType === "iris_api"
      ? "낮음"
      : ["exportvoucher_html", "kstartup_html"].includes(collectorType)
        ? "중간"
        : "높음";

  const normalized: SiteRecord = {
    id,
    name,
    type: collectorType,
    url,
    enabled: input.enabled !== false,
    is_aggregator: Boolean(input.isAggregator),
    note: [category, input.note].filter(Boolean).join(" — ").trim() || category,
    ...(needsSelectors ? { selectors: { row: "table tbody tr" } } : {}),
  };

  return {
    ok: errors.length === 0,
    errors,
    warnings,
    normalized,
    checks: {
      collectorRegistered,
      urlReachable: null,
      dateUnknownRisk,
      dryRunReady: collectorRegistered,
      stableIdNote:
        "목록에 공고 ID가 없으면 stable_id(title+link) 사용 — URL 변경 시 다른 공고로 인식될 수 있음",
    },
  };
}

export async function probeUrlReachable(url: string, timeoutMs = 8000): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    const res = await fetch(url, {
      method: "HEAD",
      signal: ctrl.signal,
      redirect: "follow",
    });
    clearTimeout(t);
    return res.ok || res.status === 405;
  } catch {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      const res = await fetch(url, { method: "GET", signal: ctrl.signal, redirect: "follow" });
      clearTimeout(t);
      return res.ok;
    } catch {
      return false;
    }
  }
}
