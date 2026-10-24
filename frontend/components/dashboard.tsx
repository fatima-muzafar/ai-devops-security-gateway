"use client";

import { useCallback, useState } from "react";
import ApprovalsPanel from "./approvals-panel";
import EventsPanel from "./events-panel";
import Hero from "./hero";
import { Icon, LogoMark } from "./icons";
import LoginForm, { type Session } from "./login-form";
import ServicesPanel from "./services-panel";

export default function Dashboard() {
  // The token lives in React memory only (decisions.md #95): a page reload logs out.
  const [session, setSession] = useState<Session | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<"hero" | "login">("hero"); // decisions.md #105
  const [reloadKey, setReloadKey] = useState(0);

  const handleLoggedIn = useCallback((s: Session) => {
    setNotice(null);
    setSession(s);
  }, []);
  const handleUnauthorized = useCallback(() => {
    setSession(null);
    setView("login");
    setNotice("Session expired. Please log in again.");
  }, []);
  const handleLogout = useCallback(() => {
    setSession(null);
    setNotice(null);
    setView("hero");
  }, []);
  const showLogin = useCallback(() => setView("login"), []);
  const showHero = useCallback(() => setView("hero"), []);
  const reloadAll = useCallback(() => setReloadKey((k) => k + 1), []);

  if (!session) {
    if (view === "hero") return <Hero onGetStarted={showLogin} />;
    return (
      <main className="login-page">
        <LoginForm notice={notice} onLoggedIn={handleLoggedIn} onBack={showHero} />
      </main>
    );
  }

  // Layout: icon sidebar + top header (decisions.md #106)
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <LogoMark />
        </div>
        <nav className="sidebar-nav">
          <a className="side-link" href="#events" title="Security Events" aria-label="Security Events">
            <Icon kind="events" />
          </a>
          <a className="side-link" href="#approvals" title="Approvals" aria-label="Approvals">
            <Icon kind="approvals" />
          </a>
          <a className="side-link" href="#services" title="Mock Services" aria-label="Mock Services">
            <Icon kind="services" />
          </a>
        </nav>
        <button
          className="side-link side-logout"
          type="button"
          onClick={handleLogout}
          title="Log out"
          aria-label="Log out"
        >
          <Icon kind="logout" />
        </button>
      </aside>
      <div className="shell-main">
        <header className="shell-top">
          <h1 className="shell-title">Security Gateway</h1>
          <span className="shell-sub">Admin dashboard</span>
          <span className="shell-space" />
          <span className="shell-user">{session.username}</span>
          <button className="button shell-logout" type="button" onClick={handleLogout}>
            Log out
          </button>
        </header>
        <main className="content">
          <EventsPanel
            token={session.token}
            reloadKey={reloadKey}
            onUnauthorized={handleUnauthorized}
          />
          <ApprovalsPanel
            token={session.token}
            reloadKey={reloadKey}
            onUnauthorized={handleUnauthorized}
            onDecided={reloadAll}
          />
          <ServicesPanel
            token={session.token}
            reloadKey={reloadKey}
            onUnauthorized={handleUnauthorized}
          />
        </main>
      </div>
    </div>
  );
}
