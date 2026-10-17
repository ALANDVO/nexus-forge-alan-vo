import { useEffect, useState } from "react";
import { exportResults, listResults } from "../api";
import type { Paged, ResultRow } from "../api";
import { Badge } from "./Loading";
import { EmptyState, ErrorState, Loading } from "./Loading";

export function ResultView({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<Paged<ResultRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [q, setQ] = useState("");

  const load = async () => {
    setError(null);
    try {
      const result = await listResults({ label: label || undefined, q: q || undefined });
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, []);

  const applyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    load();
  };
  const downloadCsv = async () => {
    const text = await exportResults({ label: label || undefined });
    const blob = new Blob([text], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "nexus-forge-results.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }
  if (loading) {
    return <Loading label="Loading results…" />;
  }

  const rows = data?.items ?? [];
  return (
    <section>
      <header style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
        <button onClick={onBack}>← Back</button>
        <h2>Results ledger</h2>
      </header>

      <form onSubmit={applyFilters} className="card" style={{ marginBottom: "1rem", display: "grid", gap: "0.5rem", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))" }}>
        <label>
          Label
          <select value={label} onChange={(e) => setLabel(e.target.value)}>
            <option value="">all</option>
            <option value="passed">passed</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <label>
          Search
          <input type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder="log text…" />
        </label>
        <div style={{ alignSelf: "flex-end" }}>
          <button type="submit">Filter</button>
          <button type="button" onClick={downloadCsv} style={{ marginLeft: "0.5rem" }}>
            Export CSV
          </button>
        </div>
      </form>

      {rows.length === 0 ? (
        <EmptyState title="No results match the current filters." />
      ) : (
        <div className="card">
          <p style={{ color: "#475569" }}>{data?.total ?? 0} result(s)</p>
          <table className="table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Plan</th>
                <th>Result</th>
                <th>Agreement</th>
                <th>Duration (ms)</th>
                <th>Last line</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.task_id}>
                  <td>{r.title}</td>
                  <td>{r.plan_name}</td>
                  <td>
                    <Badge status={r.label} />{" "}
                    <span style={{ fontSize: "0.8rem", color: "#475569" }}>
                      {Math.round(r.confidence * 100)}%
                    </span>
                  </td>
                  <td>{r.agreement}</td>
                  <td>{r.duration_ms}</td>
                  <td style={{ fontFamily: "ui-monospace", fontSize: "0.8rem" }}>{r.last_line}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

ResultView.displayName = "ResultView";