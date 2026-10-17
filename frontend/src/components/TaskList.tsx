import { useEffect, useState } from "react";
import { Badge } from "./Loading";
import { getPlan, runTask, DEMO_COMMAND } from "../api";
import type { Plan, Task, Outcome, PlanDetail, RunOptions } from "../api";
import { EmptyState, ErrorState, Loading } from "./Loading";

export function PlanDetail({
  planId,
  onBack,
  onResults,
}: { planId: string; onBack: () => void; onResults: () => void }) {
  const [plan, setPlan] = useState<PlanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [command, setCommand] = useState(DEMO_COMMAND);
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});

  const load = async () => {
    setError(null);
    try {
      const p = await getPlan(planId);
      setPlan(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    }
  };
  useEffect(() => {
    load();
  }, [planId]);

  const handleRun = async (task: Task) => {
    setRunning(task.id);
    setError(null);
    try {
      const opts: RunOptions = { command };
      const outcome = await runTask(task.id, opts);
      setOutcomes((prev) => ({ ...prev, [task.id]: outcome }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "run failed");
    } finally {
      setRunning(null);
    }
  };

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }
  if (!plan) {
    return <Loading label="Loading plan…" />;
  }
  const tasks = plan.tasks;
  return (
    <section>
      <header style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
        <button onClick={onBack}>← Back</button>
        <h2 style={{ flex: 1 }}>{plan.name}</h2>
        <button onClick={onResults}>View results</button>
      </header>

      <div className="card" style={{ marginTop: "1rem", marginBottom: "1rem" }}>
        <label>
          Demo run command
          <textarea
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            rows={2}
            style={{ width: "100%", fontFamily: "ui-monospace" }}
          />
        </label>
      </div>

      {tasks.length === 0 ? (
        <EmptyState title="This plan has no tasks." />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Task</th>
              <th>Status</th>
              <th>Result</th>
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t, i) => {
              const outcome = outcomes[t.id];
              return (
                <tr key={t.id}>
                  <td>{i + 1}</td>
                  <td>{t.title}</td>
                  <td>
                    <Badge status={outcome ? outcome.label : t.status} />
                  </td>
                  <td>
                    {outcome ? (
                      <span style={{ fontSize: "0.8rem", color: "#475569" }}>
                        {outcome.label} · exit {outcome.exit_code ?? "n/a"} ·
                        {Math.round(outcome.confidence * 100)}% · {outcome.duration_ms}ms
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <button onClick={() => handleRun(t)} disabled={running === t.id}>
                      {running === t.id ? "Running…" : "Run"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

PlanDetail.displayName = "PlanDetail";