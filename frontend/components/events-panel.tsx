"use client";

import { getEvents } from "@/lib/api";
import { decisionClass, formatTime, reasonsText, riskText } from "@/lib/format";
import { usePanelData } from "@/lib/use-panel-data";

interface Props {
  token: string;
  reloadKey: number;
  onUnauthorized: () => void;
}

export default function EventsPanel({ token, reloadKey, onUnauthorized }: Props) {
  const { data, error, loading, refreshing, reload } = usePanelData(
    getEvents,
    token,
    reloadKey,
    onUnauthorized,
  );

  return (
    <section className="panel" id="events">
      <div className="panel-head">
        <h2 className="panel-title">Security Events</h2>
        <span className="panel-sub">Latest 50, newest first</span>
        <button className="button" type="button" onClick={reload} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      {error && <p className="notice notice-error">{error}</p>}
      {loading && <p className="state">Loading...</p>}
      {data && data.length === 0 && <p className="state">No events yet.</p>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Request ID</th>
                <th>Requester</th>
                <th>Service</th>
                <th>Env</th>
                <th>Tool</th>
                <th>Decision</th>
                <th>Execution</th>
                <th>Risk</th>
                <th>Risk reasons</th>
                <th>Approval</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.request_id}>
                  <td>{formatTime(e.created_at)}</td>
                  <td className="mono">{e.request_id}</td>
                  <td>{e.requester ?? ""}</td>
                  <td>{e.service_name ?? ""}</td>
                  <td>{e.environment ?? ""}</td>
                  <td>{e.tool ?? ""}</td>
                  <td>
                    <span className={decisionClass(e.decision)}>{e.decision ?? "none"}</span>
                  </td>
                  <td>{e.execution_status}</td>
                  <td>{riskText(e.risk)}</td>
                  <td className="muted">{reasonsText(e.risk)}</td>
                  <td>{e.approval_status ?? ""}</td>
                  <td>{e.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
