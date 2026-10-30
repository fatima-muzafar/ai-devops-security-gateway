"use client";

import { useState, type FormEvent } from "react";
import { ApiError, login } from "@/lib/api";
import { LogoMark } from "./icons";

export interface Session {
  token: string;
  username: string;
}

interface Props {
  notice: string | null;
  onLoggedIn: (session: Session) => void;
  onBack?: () => void;
}

export default function LoginForm({ notice, onLoggedIn, onBack }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const name = username.trim();
    try {
      const result = await login(name, password);
      setPassword("");
      onLoggedIn({ token: result.access_token, username: name });
    } catch (err) {
      // A 401 here means wrong credentials, not an expired session (decisions.md #104).
      setError(err instanceof ApiError ? err.message : "Login failed.");
      setBusy(false);
    }
  }

  return (
    <form className="login-card" onSubmit={handleSubmit}>
      <div className="login-brand">
        <span className="login-logo">
          <LogoMark />
        </span>
        <h1 className="login-title">Security Gateway</h1>
      </div>
      <p className="muted login-sub">Log in with your account.</p>
      {notice && <p className="notice">{notice}</p>}
      {error && <p className="notice notice-error">{error}</p>}
      <label className="field">
        <span>Username</span>
        <input
          className="input"
          type="text"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </label>
      <label className="field">
        <span>Password</span>
        <input
          className="input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      <button className="button button-primary" type="submit" disabled={busy}>
        {busy ? "Logging in..." : "Log in"}
      </button>
      {onBack && (
        <button className="button login-back" type="button" onClick={onBack} disabled={busy}>
          Back to home
        </button>
      )}
    </form>
  );
}
