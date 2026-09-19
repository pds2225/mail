"use client";

import { useState } from "react";

export type ManualPendingResult = {
  manualPasteRequired?: boolean;
  githubCommitUrl?: string;
  manualFilePath?: string;
  manualContent?: string;
  pendingFileExists?: boolean;
  pendingFilename?: string;
  pendingContent?: string;
};

export default function ManualPendingApply({ result }: { result: ManualPendingResult | null }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");

  if (!result?.manualPasteRequired) return null;

  const content = String(result.manualContent || result.pendingContent || "");
  const filename = String(result.manualFilePath || result.pendingFilename || "저장 파일");
  const url = String(result.githubCommitUrl || "#");
  const finalFileMode = Boolean(result.manualFilePath);

  async function copyPendingContent() {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setCopyError("");
    } catch {
      setCopied(false);
      setCopyError("자동 복사가 막혔습니다. 아래 데이터 상자를 길게 눌러 직접 복사하세요.");
    }
  }

  return (
    <div className="mt">
      <p className="hint">
        {finalFileMode
          ? `GitHub에서 최종 파일 ${filename}이 열립니다. 기존 내용을 전체 선택해 지운 뒤 아래 전체 내용을 붙여넣으세요.`
          : result.pendingFileExists
            ? `GitHub에서 기존 ${filename} 파일이 열립니다. 기존 내용을 전체 선택해 지운 뒤 아래 데이터를 붙여넣으세요.`
            : `GitHub에서 새 ${filename} 파일이 열립니다. 아래 데이터를 파일 본문에 붙여넣으세요.`}
      </p>
      <div className="row mt" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
        <button type="button" className="btn btn-primary" onClick={copyPendingContent}>
          {copied ? "복사 완료" : "1. 저장 데이터 복사"}
        </button>
        <a className="btn btn-secondary" href={url} target="_blank" rel="noopener noreferrer">
          2. GitHub 저장 화면 열기
        </a>
      </div>
      {copyError ? <p className="error">{copyError}</p> : null}
      <textarea
        readOnly
        value={content}
        aria-label="GitHub 저장 데이터"
        rows={5}
        style={{ width: "100%", fontFamily: "monospace", marginTop: "0.75rem" }}
      />
      <p className="hint">붙여넣은 뒤 Commit changes를 누르세요.</p>
    </div>
  );
}
