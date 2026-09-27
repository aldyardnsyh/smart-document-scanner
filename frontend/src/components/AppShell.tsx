"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { getHealth } from "../lib/api";
import { Icon } from "./Icon";
import { Logo } from "./Logo";

const navigation = [
  { href: "/", label: "Overview" },
  { href: "/scanner", label: "Scanner" },
  { href: "/history", label: "History" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");
  const [engine, setEngine] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    const saved = window.localStorage.getItem("scanner-theme");
    const initial = saved === "dark" ? "dark" : "light";
    setTheme(initial);
    document.documentElement.dataset.theme = initial;
  }, []);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((report) => {
        if (!active) return;
        setHealth("online");
        // Read the engine name from the service instead of hardcoding it, so the footer
        // always states what is actually running.
        setEngine(report.ocr_engine_available ? report.ocr_engine : "OCR unavailable");
      })
      .catch(() => active && setHealth("offline"));
    return () => {
      active = false;
    };
  }, []);

  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("scanner-theme", next);
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="topbar">
        <div className="topbar__inner">
          <Link aria-label="Smart Document Scanner home" className="topbar__brand" href="/">
            <Logo />
          </Link>
          <button
            aria-expanded={menuOpen}
            aria-label="Toggle navigation"
            className="menu-button"
            onClick={() => setMenuOpen((value) => !value)}
            type="button"
          >
            <span />
            <span />
            <span />
          </button>
          <nav className={menuOpen ? "main-nav is-open" : "main-nav"} aria-label="Main navigation">
            {navigation.map((item) => (
              <Link
                className={pathname === item.href ? "active" : ""}
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            ))}
            <a href="/docs" target="_blank" rel="noreferrer">API Docs</a>
          </nav>
          <div className="topbar__utilities">
            <span className={`api-status api-status--${health}`}>
              <i />
              {health === "checking" ? "Checking API" : health === "online" ? "FastAPI Online" : "API Offline"}
            </span>
            <button
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
              className="icon-button"
              onClick={toggleTheme}
              type="button"
            >
              <Icon name={theme === "light" ? "moon" : "sun"} size={18} />
            </button>
          </div>
        </div>
      </header>
      <main id="main-content">{children}</main>
      <footer className="footer">
        <div>
          <span>OpenCV</span>
          <span>Perspective correction</span>
          {engine ? <span>{engine}</span> : null}
          <span>FastAPI</span>
        </div>
        <p>Smart Document Scanner</p>
      </footer>
    </div>
  );
}
