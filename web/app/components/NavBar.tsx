"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ApplySecretField from "./ApplySecretField";

const LINKS = [
  { href: "/", label: "홈" },
  { href: "/sites", label: "소스 관리" },
  { href: "/groups", label: "그룹 관리" },
  { href: "/settings", label: "설정" },
  { href: "/run", label: "실행" },
  { href: "/review", label: "공고 검수" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="app-header">
      <nav className="nav" aria-label="주요 메뉴">
        <Link href="/" className="brand">
          <span className="brand-dot" aria-hidden="true" />
          정부지원사업 메일링
        </Link>
        <div className="nav-links">
          {LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={active ? "nav-link active" : "nav-link"}
                aria-current={active ? "page" : undefined}
              >
                {link.label}
              </Link>
            );
          })}
          <ApplySecretField />
        </div>
      </nav>
    </header>
  );
}
