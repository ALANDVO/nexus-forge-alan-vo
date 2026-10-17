import { useState } from "react";
import { PlanDashboard } from "./components/PlanDashboard";
import { PlanDetail } from "./components/TaskList";
import { ResultView } from "./components/ResultView";

export type View = { mode: "dashboard" } | { mode: "plan"; id: string } | { mode: "results" };

export function App() {
  const [view, setView] = useState<View>({ mode: "dashboard" });

  return (
    <div className="container">
      <header>
        <h1 style={{ margin: 0 }}>
          Nexus Forge
          <span style={{ color: "#475569", fontSize: "0.9rem", marginLeft: "0.5rem" }}>
            | Alan Vo | AI & Machine Learning
          </span>
        </h1>
        <nav style={{ marginTop: "0.5rem" }}>
          <button onClick={() => setView({ mode: "dashboard" })}>Plans</button>
          <button onClick={() => setView({ mode: "results" })} style={{ marginLeft: "0.5rem" }}>
            Results
          </button>
        </nav>
      </header>
      <main>
        {view.mode === "dashboard" && <PlanDashboard onView={(id) => setView({ mode: "plan", id })} />}
        {view.mode === "plan" && (
          <PlanDetail
            planId={view.id}
            onBack={() => setView({ mode: "dashboard" })}
            onResults={() => setView({ mode: "results" })}
          />
        )}
        {view.mode === "results" && <ResultView onBack={() => setView({ mode: "dashboard" })} />}
      </main>
    </div>
  );
}

App.displayName = "App";