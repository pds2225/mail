import type { Metadata } from "next";
import "./globals.css";
import NavBar from "./components/NavBar";

export const metadata: Metadata = {
  title: "정부지원사업 메일링",
  description: "정부지원사업 수집·추천조건·실행·공고검수를 한곳에서 관리하는 모바일 운영 화면",
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
