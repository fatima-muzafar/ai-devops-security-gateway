"use client";

import { useCallback, useState } from "react";
import { ApiError, decideApproval, getApprovals } from "@/lib/api";
import { formatTime, reasonsText, riskText } from "@/lib/format";
import { usePanelData } from "@/lib/use-panel-data";
import type { ApprovalItem, ApprovalStatus, DecisionResult } from "@/lib/types";

const STATUSES: ApprovalStatus[] = ["pending", "approved", "rejected"];

interface Props {
  token: string;
  reloadKey: number;
  onUnauthorized: () => void;
  onDecided: () => void;
}

interface Message {
  kind: "ok" | "error";
  text: string;
}

// The UI only shows what the server answered (decisions.md #98); it decides nothing.
function describe(result: DecisionResult): Message {
  if (result.outcome === "executed") {
    return { kind: "ok", text: `Approved and executed (request ${result.request_id}).` };
  }
  if (result.outcome === "revalidation_failed") {
    return {
      kind: "error",
      text: `Approved, but revalidation failed, so nothing ran: ${result.reason ?? ""}`,
    };
  }
  return { kind: "ok", text: `Rejected (request ${result.request_id}).` };
}

export default function ApprovalsPanel({ token, reloadKey, onUnauthorized, onDecided }: Props) {
  const [status, setStatus] = useState<ApprovalStatus>("pending");
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState<Message | null>(null);

  const load = useCallback((t: string) => getApprovals(t, status), [status]);
  const { data, error, loading, refreshing, reload } = usePanelData(
    load,
    token,
    reloadKey,
    onUnauthorized,
    status,
  );

  async function act(item: ApprovalItem, action: "approve" | "reject") {
    const reason = (reasons[item.id] ?? "").trim();
    if (action === "reject" && !reason) {
      setMessage({ kind: "error", text: "A reason is required to reject." });
      return;
    }
    setBusyId(item.id);
    setMessage(null);
    try {
      const result = await decideApproval(token, item.id, action, reason);
      setMessage(describe(result));
      onDecided();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setMessage({
        kind: "error",
        text: err instanceof ApiError ? `HTTP ${err.status}: ${err.message}` : "Unexpected error.",
      });
      onDecided(); // a 409 or 502 may mean the state changed; show the real list
    } finally {
      setBusyId(null);
    }
  }

  const pending = status === "pending";

  return (
    <section className="panel" id="approvals">
      <div className="panel-head">
        <h2 className="panel-title">Approvals</h2>
        <label className="panel-sub">
          Status{" "}
          <select
            className="input"
            value={status}
            onChange={(e) => setStatus(e.target.value as ApprovalStatus)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <button className="button" type="button" onClick={reload} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      {message && (
        <p className={message.kind === "ok" ? "notice notice-ok" : "notice notice-error"}>
          {message.text}
        </p>
      )}
      {error && <p className="notice notice-error">{error}</p>}
      {loading && <p className="state">Loading...</p>}
      {data && data.length === 0 && <p className="state">No {status} approvals.</p>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Request ID</th>
                <th>Requester</th>
                <th>Agent</th>
                <th>Service</th>
                <th>Env</th>
                <th>Tool</th>
                <th>Arguments</th>
                <th>Risk</th>
                <th>Risk reasons</th>
                {pending ? (
                  <th>Decision</th>
                ) : (
                  <>
                    <th>Reviewer</th>
                    <th>Decided</th>
                    <th>Reviewer reason</th>
                    <th>Revalidation</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td>{formatTime(a.created_at)}</td>
                  <td className="mono">{a.request_id}</td>
                  <td>{a.requester ?? ""}</td>
                  <td>{a.agent ?? ""}</td>
                  <td>{a.service_name ?? ""}</td>
                  <td>{a.environment ?? ""}</td>
                  <td>{a.tool ?? ""}</td>
                  <td className="mono">{JSON.stringify(a.arguments)}</td>
                  <td>{riskText(a.risk)}</td>
                  <td className="muted">{reasonsText(a.risk)}</td>
                  {pending ? (
                    <td>
                      <div className="actions">
                        <input
                          className="input"
                          type="text"
                          placeholder="Reason (required to reject)"
                          value={reasons[a.id] ?? ""}
                          onChange={(e) => setReasons({ ...reasons, [a.id]: e.target.value })}
                          disabled={busyId !== null}
                        />
                        <button
                          className="button button-primary"
                          type="button"
                          onClick={() => act(a, "approve")}
                          disabled={busyId !== null}
                        >
                          Approve
                        </button>
                        <button
                          className="button button-danger"
                          type="button"
                          onClick={() => act(a, "reject")}
                          disabled={busyId !== null}
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  ) : (
                    <>
                      <td>{a.reviewer ?? ""}</td>
                      <td>{formatTime(a.decided_at)}</td>
                      <td>{a.reason ?? ""}</td>
                      <td>{a.revalidation ?? ""}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
