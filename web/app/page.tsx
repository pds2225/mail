import Link from "next/link";

export default function HomePage() {
  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">수출·지원사업 모니터</h1>
        <p className="page-desc">
          사이트 목록을 보고, 추가·수정한 뒤 <strong>GitHub에 반영</strong>하면 운영{" "}
          <code>config/sites.json</code>이 바로 바뀝니다. 메일 발송은 하지 않습니다.
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
            수신자
          </Link>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">쓰는 방법</h2>
        <ol>
          <li>오른쪽 위 <strong>반영 암호</strong>에 Vercel <code>CONFIG_APPLY_SECRET</code>을 입력</li>
          <li>사이트 추가 또는 편집</li>
          <li>
            <strong>GitHub에 반영</strong> → <code>main</code>의 <code>config/sites.json</code> 커밋
          </li>
          <li>1~2분 뒤 이 화면 목록이 갱신됩니다</li>
        </ol>
      </section>

      <section className="card">
        <h2 className="card-title">안 하는 일</h2>
        <ul>
          <li>실제 메일 발송 없음</li>
          <li>수신자 이메일은 GitHub JSON에 없습니다 (암호화 private store)</li>
        </ul>
      </section>
    </div>
  );
}
