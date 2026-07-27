import Link from "next/link";

export default function HomePage() {
  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">수출·지원사업 모니터 — Vercel 관리</h1>
        <p className="page-desc">
          GitHub 레포의 <code>config/sites.json</code>, <code>config/groups.json</code>,{" "}
          <code>config/settings.json</code>을 원본으로 읽습니다. 이 UI는 운영 파일을 직접 수정하지 않고,
          검증 후 PR 패킷을 생성합니다.
        </p>
      </header>

      <section className="card">
        <h2 className="card-title">바로 가기</h2>
        <div className="row">
          <Link className="btn btn-primary" href="/sites/add">
            ＋ 사이트 추가
          </Link>
          <Link className="btn btn-secondary" href="/sites">
            사이트 목록
          </Link>
          <Link className="btn btn-secondary" href="/recipients">
            수신자 검증
          </Link>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">데이터 흐름</h2>
        <ol>
          <li>Vercel UI에서 사이트·수신자 입력</li>
          <li>URL·중복·collector 검증</li>
          <li>
            <code>WORKS/SITE_ADD_PR_PACKET.md</code> 또는 API 응답으로 패킷 다운로드
          </li>
          <li>브랜치 + PR → 사용자 승인 → merge</li>
        </ol>
      </section>

      <section className="card">
        <h2 className="card-title">금지 사항</h2>
        <ul>
          <li>실제 메일 발송 / seen_ids 저장 변경 없음</li>
          <li>main 직접 수정·PR auto merge 없음</li>
          <li>임의 사이트·이메일 자동 반영 없음</li>
        </ul>
      </section>
    </div>
  );
}
