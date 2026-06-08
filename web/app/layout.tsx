import type { Metadata } from "next";
import "./globals.css";
import NavBar from "./components/NavBar";

export const metadata: Metadata = {
  title: "Mail Monitor Admin",
  description: "사이트·수신자 설정 관리 (GitHub PR 패킷)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <NavBar />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
