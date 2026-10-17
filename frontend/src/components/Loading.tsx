import { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="card" role="status" aria-label={label}>
      <div className="spinner" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: { message: string; onRetry?: () => void }) {
  return (
    <div className="card" role="alert" style={{ color: "#b91c1c" }}>
      <strong>Something went wrong</strong>
      <pre style={{ whiteSpace: "pre-wrap" }}>{message}</pre>
      {onRetry && <button onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function EmptyState({
  title,
  actionLabel,
  onAction,
}: { title: string; actionLabel?: string; onAction?: () => void }) {
  return (
    <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
      <p style={{ color: "#64748b" }}>{title}</p>
      {actionLabel && onAction && (
        <button onClick={onAction} style={{ marginTop: "0.5rem" }}>{actionLabel}</button>
      )}
    </div>
  );
}

export function Badge({ status }: { status: string }) {
  const cls = status === "passed" ? "badge pass" : status === "failed" ? "badge fail" : "badge pending";
  return <span className={cls}>{status}</span>;
}

export function Stack({ children, gap = "1rem" }: { children: ReactNode; gap?: string }) {
  return <div style={{ display: "grid", gap, alignItems: "start" }}>{children}</div>;
}