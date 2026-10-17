import { useEffect, useState } from "react";
import { Badge } from "./Loading";
import { classifyMetrics, listPlans, createPlan } from "../api";
import type { Plan, Paged, Metrics } from "../api";
import { EmptyState, ErrorState, Loading } from "./Loading";

export function PlanDashboard({ onView }: { onView: (id: string) => void }) {
  const [plans, setPlans] = useState<Paged<Plan> | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setError(null);
    try {
      const p = await listPlans();
      setPlans(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !text || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await createPlan(name, text);
      setName("");
      setText("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "create failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }
  if (loading) {
    return <Loading label="Loading plans…" />;
  }

  const items = plans?.items ?? [];
  return (
    <section>
      <header>
        <h1>Nexus Forge</h1>
        <p>Agentic plan ledger with ML outcome classification.</p>
      </header>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h2>Create a plan</h2>
        <form onSubmit={handleSubmit} style={{ display: "grid", gap: "0.5rem" }}>
          <input
            type="text"
            placeholder="Plan name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <textarea
            placeholder={"- [ ] task one\n- [ ] task two"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            required
          />
          <button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create plan"}
          </button>
        </form>
      </div>

      {items.length === 0 ? (
        <EmptyState title="No plans yet." actionLabel="Create your first plan above" />
      ) : (
        <div className="card">
          <h2>Plans ({plans?.total ?? 0})</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Tasks</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{p.task_count}</td>
                  <td>{p.created_at?.slice(0, 10) ?? "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    <button onClick={() => onView(p.id)}>Open</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ModelMetricsCard />
    </section>
  );
}

function ModelMetricsCard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    classifyMetrics()
      .then(setMetrics)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : "metrics unavailable"));
  }, []);

  if (!metrics) {
    return <Loading label="Loading model metrics…" />;
  }
  return (
    <div className="card" style={{ marginTop: "1.5rem" }}>
      <h2>Outcome classifier metrics</h2>
      <p style={{ color: "#475569" }}>
        Offline logistic-regression log classifier trained on {metrics.dataset_size} labeled
        runner outputs (no LLM key).
      </p>
      <table className="table">
        <tbody>
          <tr>
            <th>Accuracy</th>
            <td>{metrics.accuracy}</td>
          </tr>
          <tr>
            <th>F1</th>
            <td>{metrics.f1}</td>
          </tr>
          <tr>
            <th>Precision</th>
            <td>{metrics.precision}</td>
          </tr>
          <tr>
            <th>Recall</th>
            <td>{metrics.recall}</td>
          </tr>
          <tr>
            <th>Split</th>
            <td>
              {metrics.train_size} train / {metrics.test_size} test
            </td>
          </tr>
        </tbody>
      </table>
      {err && <p style={{ color: "#b91c1c" }}>{err}</p>}
    </div>
  );
}

ModelMetricsCard.displayName = "ModelMetricsCard";
PlanDashboard.displayName = "PlanDashboard";