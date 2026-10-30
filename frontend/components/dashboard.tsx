"use client";

import { useCallback, useState } from "react";
import ApprovalsPanel from "./approvals-panel";
import ChatPanel from "./chat-panel";
import EventsPanel from "./events-panel";
import Hero from "./hero";
import { Icon, LogoMark } from "./icons";
import LoginForm, { type Session } from "./login-form";
import ServicesPanel from "./services-panel";

type Tab = "chat" | "dashboard";

export default function Dashboard() {
  // The token lives in React memory only (decisions.md #95): a page reload logs out.
  const [session, setSession] = useState<Session | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<"hero" | "login">("hero"); // decisions.md #105
  const [tab, setTab] = useState<Tab>("chat"); // decisions.md #108: chat first, for every role
  const [reloadKey, setReloadKey] = useState(0);

  const handleLoggedIn = useCallback((s: Session) => {
    setNotice(null);
    setTab("chat");
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

  // Layout: icon sidebar + top header (decisions.md #106, #108). Both views stay mounted;
  // the inactive one is hidden so the chat transcript and the panel data survive a tab switch.
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <LogoMark />
        </div>
        <nav className="sidebar-nav">
          <button
            className={tab === "chat" ? "side-link side-link-active" : "side-link"}
            type="button"
            onClick={() => setTab("chat")}
            title="Chat with the agent"
            aria-label="Chat with the agent"
          >
            <Icon kind="chat" />
          </button>
          <button
            className={tab === "dashboard" ? "side-link side-link-active" : "side-link"}
            type="button"
            onClick={() => setTab("dashboard")}
            title="Admin dashboard"
            aria-label="Admin dashboard"
          >
            <Icon kind="dashboard" />
          </button>
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
          <span className="shell-sub">{tab === "chat" ? "DevOps agent chat" : "Admin dashboard"}</span>
          <span className="shell-space" />
          <span className="shell-user">{session.username}</span>
          <button className="button shell-logout" type="button" onClick={handleLogout}>
            Log out
          </button>
        </header>
        <main className="content" hidden={tab !== "chat"}>
          <ChatPanel token={session.token} onUnauthorized={handleUnauthorized} />
        </main>
        <main className="content" hidden={tab !== "dashboard"}>
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
