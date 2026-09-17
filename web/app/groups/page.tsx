"use client";

import { useEffect, useMemo, useState } from "react";
import { applyHeaders, followApplyResult } from "@/lib/apply-client";

const REGIONS = [
  "서울",
  "부산",
  "대구",
  "인천",
  "광주",
  "대전",
  "울산",
  "세종",
  "경기",
  "강원",
  "충북",
  "충남",
  "전북",
  "전남",
  "경북",
  "경남",
  "제주",
];
const SUPPORT_TYPES = ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"];

type Group = {
  id: string;
  name: string;
  active?: boolean;
  required_conditions?: { regions?: string[] };
  or_keywords?: string[];
  and_keyword_groups?: string[][];
  exclude_keywords?: string[];
  support_types?: string[];
  recipients?: string[];
};

type Draft = {
  name: string;
  active: boolean;
  regions: string[];
  orKeywords: string;
  andGroups: string;
  excludeKeywords: string;
  supportTypes: string[];
};

function lines(values: string[] | undefined) {
  return (values || []).join("\n");
}

function parseLines(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseAndGroups(value: string) {
  return value
    .split("\n")
    .map((line) =>
      line
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    )
    .filter((group) => group.length > 0);
}

function draftFromGroup(group: Group): Draft {
  return {
    name: group.name,
    active: group.active !== false,
    regions: group.required_conditions?.regions || [],
    orKeywords: lines(group.or_keywords),
    andGroups: (group.and_keyword_groups || []).map((row) => row.join(", ")).join("\n"),
    excludeKeywords: lines(group.exclude_keywords),
    supportTypes: group.support_types || SUPPORT_TYPES,
  };
}

export default function GroupsPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.json())
      .then((payload) => {
        if (!payload.ok) throw new Error(payload.error || "그룹을 불러오지 못했습니다.");
        const rows = (payload.groups || []) as Group[];
        setGroups(rows);
        setDrafts(Object.fromEntries(rows.map((group) => [group.id, draftFromGroup(group)])));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const activeCount = useMemo(() => groups.filter((group) => group.active !== false).length, [groups]);

  function update(id: string, patch: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [id]: { ...current[id], ...patch } }));
    setResult(null);
  }

  async function save(id: string) {
    const draft = drafts[id];
    if (!draft) return;
    setSaving(id);
    setError("");
    try {
      const response = await fetch("/api/config/apply", {
        method: "POST",
        headers: applyHeaders(),
        body: JSON.stringify({
          resource: "group",
          id,
          patch: {
            name: draft.name.trim(),
            active: draft.active,
            required_conditions: { regions: draft.regions },
            or_keywords: parseLines(draft.orKeywords),
            and_keyword_groups: parseAndGroups(draft.andGroups),
            exclude_keywords: parseLines(draft.excludeKeywords),
            support_types: draft.supportTypes,
          },
        }),
      });
      const data = await response.json();
      setResult(data);
      if (!response.ok || !data.ok) throw new Error(data.error || "저장하지 못했습니다.");
      followApplyResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving("");
    }
  }

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">그룹 관리</h1>
        <p className="page-desc">
          V1 방식으로 지역 → 포함 키워드 → AND → 제외 키워드 → 지원유형 순서로 관리합니다. 활성 {activeCount} / 전체 {groups.length}
        </p>
      </header>

      {error ? <p className="error">{error}</p> : null}
      {loading ? <div className="empty">불러오는 중…</div> : null}

      {groups.map((group) => {
        const draft = drafts[group.id];
        if (!draft) return null;
        return (
          <details className="card disclosure" key={group.id}>
            <summary className="disclosure-summary">
              <span>
                <strong>{draft.name}</strong>
                <span className="hint-inline"> · {draft.regions.join(", ") || "전국"}</span>
              </span>
              <span className={draft.active ? "badge badge-green" : "badge badge-gray"}>
                {draft.active ? "활성" : "비활성"}
              </span>
            </summary>

            <div className="mt">
              <div className="grid2">
                <div className="field">
                  <label className="label" htmlFor={`name-${group.id}`}>그룹명</label>
                  <input
                    id={`name-${group.id}`}
                    className="input"
                    value={draft.name}
                    onChange={(event) => update(group.id, { name: event.target.value })}
                  />
                </div>
                <label className="check align-end">
                  <input
                    type="checkbox"
                    checked={draft.active}
                    onChange={(event) => update(group.id, { active: event.target.checked })}
                  />
                  그룹 활성화
                </label>
              </div>

              <div className="field mt">
                <span className="label">필수조건 — 지역</span>
                <div className="chip-grid">
                  {REGIONS.map((region) => (
                    <label className="check chip-check" key={region}>
                      <input
                        type="checkbox"
                        checked={draft.regions.includes(region)}
                        onChange={(event) =>
                          update(group.id, {
                            regions: event.target.checked
                              ? [...draft.regions, region]
                              : draft.regions.filter((value) => value !== region),
                          })
                        }
                      />
                      {region}
                    </label>
                  ))}
                </div>
                <p className="hint">선택하지 않으면 전국으로 취급합니다.</p>
              </div>

              <div className="grid2 mt">
                <div className="field">
                  <label className="label" htmlFor={`or-${group.id}`}>OR 키워드</label>
                  <textarea
                    id={`or-${group.id}`}
                    className="textarea keyword-area"
                    value={draft.orKeywords}
                    onChange={(event) => update(group.id, { orKeywords: event.target.value })}
                    placeholder="한 줄에 하나씩"
                  />
                </div>
                <div className="field">
                  <label className="label" htmlFor={`exclude-${group.id}`}>제외 키워드</label>
                  <textarea
                    id={`exclude-${group.id}`}
                    className="textarea keyword-area"
                    value={draft.excludeKeywords}
                    onChange={(event) => update(group.id, { excludeKeywords: event.target.value })}
                    placeholder="포함되면 제외"
                  />
                </div>
              </div>

              <div className="field mt">
                <label className="label" htmlFor={`and-${group.id}`}>AND 키워드 그룹</label>
                <textarea
                  id={`and-${group.id}`}
                  className="textarea"
                  value={draft.andGroups}
                  onChange={(event) => update(group.id, { andGroups: event.target.value })}
                  placeholder={"AI, 사업화\n수출, 바우처"}
                />
                <p className="hint">한 줄이 한 그룹이며, 같은 줄의 단어를 모두 포함하면 통과합니다.</p>
              </div>

              <div className="field mt">
                <span className="label">지원유형</span>
                <div className="check-row">
                  {SUPPORT_TYPES.map((supportType) => (
                    <label className="check" key={supportType}>
                      <input
                        type="checkbox"
                        checked={draft.supportTypes.includes(supportType)}
                        onChange={(event) =>
                          update(group.id, {
                            supportTypes: event.target.checked
                              ? [...draft.supportTypes, supportType]
                              : draft.supportTypes.filter((value) => value !== supportType),
                          })
                        }
                      />
                      {supportType}
                    </label>
                  ))}
                </div>
              </div>

              <div className="privacy-note mt">
                수신자 주소는 암호화 private store에 보관되므로 이 화면에서는 수정하지 않습니다.
                {group.recipients?.length ? ` 현재 ${group.recipients.length}개 주소가 마스킹되어 연결돼 있습니다.` : ""}
              </div>

              <div className="row mt">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => save(group.id)}
                  disabled={saving === group.id || !draft.name.trim()}
                >
                  {saving === group.id ? "저장 중…" : "그룹 저장"}
                </button>
              </div>
            </div>
          </details>
        );
      })}

      {result ? (
        <div className="card">
          <h2 className="card-title">저장 결과</h2>
          {result.error ? <p className="error">{String(result.error)}</p> : null}
          {result.notice ? <p>{String(result.notice)}</p> : null}
          {result.commitUrl ? <p className="hint">저장 커밋이 생성됐습니다.</p> : null}
        </div>
      ) : null}
    </div>
  );
}
