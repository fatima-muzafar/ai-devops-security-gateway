"use client";

import { useCallback, useState } from "react";
import ApprovalsPanel from "./approvals-panel";
import EventsPanel from "./events-panel";
import Hero from "./hero";
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

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Security Gateway</span>
        <nav className="topnav">
          <a href="#events">Security Events</a>
          <a href="#approvals">Approvals</a>
          <a href="#services">Mock Services</a>
        </nav>
        <span className="topbar-user">{session.username}</span>
        <button className="button" type="button" onClick={handleLogout}>
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
  );
}
