import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mail Monitor Admin",
  description: "사이트·수신자 설정 관리 (GitHub PR 패킷)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <nav className="nav">
          <Link href="/">개요</Link>
          <Link href="/sites">사이트</Link>
          <Link href="/sites/add">사이트 추가</Link>
          <Link href="/recipients">수신자</Link>
        </nav>
        <main style={{ maxWidth: 960, margin: "0 auto", padding: "1.5rem" }}>{children}</main>
      </body>
    </html>
  );
}
