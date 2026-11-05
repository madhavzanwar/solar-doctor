"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser, isLoggedIn, logout } from "@/lib/api";

const navItems = [
  { label: "Overview", href: "/dashboard", index: "01" },
  { label: "Plants", href: "/dashboard/plants", index: "02" },
  { label: "Forecasts", href: "/dashboard/forecasts", index: "03" },
  { label: "Alerts", href: "/dashboard/alerts", index: "04" },
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    setUser(getCurrentUser());
  }, [router]);

  return (
    <div className="dash-root site-grid">
      <aside className={`dash-sidebar${sidebarOpen ? " open" : ""}`}>
        <div className="dash-sidebar-header">
          <Link href="/dashboard" className="dash-logo">
            <span>Operations</span>
            SolarPulse AI
          </Link>
          <button
            className="dash-close-btn"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            ✕
          </button>
        </div>

        <nav className="dash-nav">
          {navItems.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`dash-nav-item${active ? " active" : ""}`}
                onClick={() => setSidebarOpen(false)}
              >
                <span className="dash-nav-index">{item.index}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="dash-sidebar-footer">
          <div className="dash-user">
            <div className="dash-user-avatar">
              {user ? user[0].toUpperCase() : "?"}
            </div>
            <div className="dash-user-info">
              <span className="dash-user-name">{user ?? "Operator"}</span>
              <span className="dash-user-role">Plant operator</span>
            </div>
          </div>
          <button className="dash-logout" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      {sidebarOpen && (
        <div
          className="dash-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <div className="dash-main">
        <header className="dash-topbar">
          <button
            className="dash-menu-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            ☰
          </button>
          <div className="dash-topbar-right">
            <span className="dash-topbar-user">{user ?? ""}</span>
          </div>
        </header>
        <main className="dash-content">{children}</main>
      </div>
    </div>
  );
}
