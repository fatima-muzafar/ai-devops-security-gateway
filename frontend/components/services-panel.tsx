"use client";

import { getServices } from "@/lib/api";
import { usePanelData } from "@/lib/use-panel-data";

interface Props {
  token: string;
  reloadKey: number;
  onUnauthorized: () => void;
}

export default function ServicesPanel({ token, reloadKey, onUnauthorized }: Props) {
  const { data, error, loading, refreshing, reload } = usePanelData(
    getServices,
    token,
    reloadKey,
    onUnauthorized,
  );

  return (
    <section className="panel" id="services">
      <div className="panel-head">
        <h2 className="panel-title">Mock Services</h2>
        <span className="panel-sub">Current state of the simulated environment</span>
        <button className="button" type="button" onClick={reload} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      {error && <p className="notice notice-error">{error}</p>}
      {loading && <p className="state">Loading...</p>}
      {data && data.length === 0 && <p className="state">No services found.</p>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Env</th>
                <th>Current version</th>
                <th>Known good version</th>
                <th>Status</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={`${s.service_name}:${s.environment}`}>
                  <td>{s.service_name}</td>
                  <td>{s.environment}</td>
                  <td>{s.current_version}</td>
                  <td>{s.known_good_version}</td>
                  <td>{s.status}</td>
                  <td>{s.owner}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
