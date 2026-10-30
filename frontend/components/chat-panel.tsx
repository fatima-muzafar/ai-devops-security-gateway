"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, sendChat } from "@/lib/api";
import { decisionClass } from "@/lib/format";
import type { ChatResult } from "@/lib/types";

// Chat with the DevOps agent (decisions.md #108-#110).
// The agent reply is untrusted LLM output: it is ALWAYS rendered as plain text (#92, #109).

const MAX_LENGTH = 2000; // UX cap only, not a security control (#109)
const EXAMPLES = [
  "Show the logs of notification-service in staging",
  "Restart notification-service in staging",
  "Restart notification-service in production",
];

type Entry =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "agent"; result: ChatResult };

interface Props {
  token: string;
  onUnauthorized: () => void;
}

export default function ChatPanel({ token, onUnauthorized }: Props) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [entries.length, busy]);

  async function send() {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError(null);
    setText("");
    const userId = nextId.current++;
    setEntries((prev) => [...prev, { id: userId, role: "user", text: message }]);
    try {
      const result = await sendChat(token, message);
      const agentId = nextId.current++;
      setEntries((prev) => [...prev, { id: agentId, role: "agent", result }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setError(
        err instanceof ApiError
          ? err.status === 0
            ? err.message
            : `HTTP ${err.status}: ${err.message}`
          : "Unexpected error.",
      );
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <section className="panel" id="chat">
      <div className="panel-head">
        <h2 className="panel-title">DevOps Agent</h2>
        <span className="panel-sub">Every action the agent proposes goes through the Security Gateway</span>
      </div>
      <div className="chat-list" ref={listRef}>
        {entries.length === 0 && !busy && (
          <div className="chat-empty">
            <p className="state">
              Ask the agent to read logs or metrics, restart, roll back or deploy a service. Try one
              of these:
            </p>
            <div className="chat-examples">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  className="button"
                  type="button"
                  onClick={() => setText(example)}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
        {entries.map((entry) =>
          entry.role === "user" ? (
            <div key={entry.id} className="chat-row chat-row-user">
              <div className="chat-bubble chat-bubble-user">{entry.text}</div>
            </div>
          ) : (
            <div key={entry.id} className="chat-row">
              <div className="chat-bubble chat-bubble-agent">
                <div className="chat-text">{entry.result.reply}</div>
                {entry.result.decision && (
                  <span className={decisionClass(entry.result.decision)}>
                    {entry.result.decision}
                  </span>
                )}
                {entry.result.tool_request && (
                  <div className="chat-meta mono">
                    agent proposed: {JSON.stringify(entry.result.tool_request)}
                  </div>
                )}
                <div className="chat-meta mono">request {entry.result.request_id}</div>
              </div>
            </div>
          ),
        )}
        {busy && (
          <div className="chat-row">
            <div className="chat-bubble chat-bubble-agent muted">Thinking...</div>
          </div>
        )}
      </div>
      {error && <p className="notice notice-error">{error}</p>}
      <form className="chat-form" onSubmit={handleSubmit}>
        <textarea
          className="input chat-input"
          rows={2}
          maxLength={MAX_LENGTH}
          placeholder="Message the DevOps agent (Enter to send, Shift+Enter for a new line)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={busy}
        />
        <button className="button button-primary" type="submit" disabled={busy || text.trim() === ""}>
          Send
        </button>
      </form>
    </section>
  );
}
