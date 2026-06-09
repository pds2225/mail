"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "개요" },
  { href: "/sites", label: "사이트" },
  { href: "/sites/add", label: "사이트 추가" },
  { href: "/recipients", label: "수신자" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="app-header">
      <nav className="nav" aria-label="주요 메뉴">
        <Link href="/" className="brand">
          <span className="brand-dot" aria-hidden="true" />
          수출·지원사업 모니터
        </Link>
        <div className="nav-links">
          {LINKS.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={active ? "nav-link active" : "nav-link"}
                aria-current={active ? "page" : undefined}
              >
                {l.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
