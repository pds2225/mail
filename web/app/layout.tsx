import type { Metadata } from "next";
import "./globals.css";
import NavBar from "./components/NavBar";

export const metadata: Metadata = {
  title: "Mail Monitor Admin",
  description: "사이트 설정을 GitHub main에 반영하는 관리 화면",
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
