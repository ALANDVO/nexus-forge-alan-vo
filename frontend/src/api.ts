/** Typed client derived directly from the backend routes and response envelopes.
 *
 * Backend Pydantic models validate every response shape server-side; here we
 * treat raw JSON as `unknown` and surface a typed view. No `any` is used.
 */
export interface Plan {
  id: string;
  name: string;
  status: string;
  task_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Task {
  id: string;
  title: string;
  body: string;
  status: string;
  order: number;
}

export interface PlanDetail extends Plan {
  text: string;
  tasks: Task[];
}

export interface Outcome {
  task_id: string;
  plan_id: string;
  label: string;
  passed: boolean;
  confidence: number;
  agreement: string;
  exit_code: number | null;
  duration_ms: number;
  last_line: string;
  head: string;
  created_at?: string | null;
}

export interface ResultRow {
  task_id: string;
  plan_id: string;
  plan_name: string;
  title: string;
  label: string;
  confidence: number;
  agreement: string;
  exit_code: number | null;
  duration_ms: number;
  last_line: string;
  head: string;
  created_at: string;
}

export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Metrics {
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  train_size: number;
  test_size: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  dataset_size: number;
  note: string;
}

export interface ClassifyResult {
  label: string;
  passed: boolean;
  confidence: number;
  agreement: string;
}

export class HttpError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "HttpError";
    this.status = status;
    this.detail = detail;
  }
}

const BASE = import.meta.env.VITE_API_URL || "";

function defaultStatusText(status: number): string {
  return `HTTP ${status}`;
}

function field(node: unknown, key: string): unknown {
  if (node && typeof node === "object") {
    const rec = node as Record<string, unknown>;
    return rec[key];
  }
  return undefined;
}

function detailToString(data: unknown, status: number, statusText: string): string {
  if (typeof data === "string") {
    try {
      return detailToString(JSON.parse(data) as unknown, status, statusText);
    } catch {
      return data || statusText;
    }
  }
  if (data && typeof data === "object") {
    const detail = field(data, "detail");
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const msg = item && typeof item === "object" ? field(item, "msg") : undefined;
          return typeof msg === "string" ? msg : String(item);
        })
        .join("; ");
    }
    if (typeof detail === "string") {
      return detail;
    }
    const message = field(data, "message");
    if (typeof message === "string") {
      return message;
    }
  }
  return statusText || defaultStatusText(status);
}

async function jsonBody<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    ...init,
  });
  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    throw new HttpError(res.status, detailToString(data, res.status, res.statusText));
  }
  // Backend Pydantic validates shape server-side; treat as typed view.
  return data as T;
}

export async function createPlan(name: string, text: string): Promise<Plan> {
  return jsonBody<Plan>("/plans", { method: "POST", body: JSON.stringify({ name, text }) });
}

export async function listPlans(limit = 25, offset = 0, name?: string): Promise<Paged<Plan>> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (name) params.set("name", name);
  return jsonBody<Paged<Plan>>(`/plans?${params}`);
}

export async function getPlan(id: string): Promise<PlanDetail> {
  return jsonBody<PlanDetail>(`/plans/${encodeURIComponent(id)}`);
}

export async function listTasks(planId: string): Promise<Task[]> {
  return getPlan(planId).then((plan) => plan.tasks);
}

export interface RunOptions {
  command: string;
  timeout?: number;
}
export async function runTask(taskId: string, opts: RunOptions): Promise<Outcome> {
  const cmd = opts.command.trim() ? ["sh", "-c", opts.command] : [];
  return jsonBody<Outcome>(`/tasks/${encodeURIComponent(taskId)}/run`, {
    method: "POST",
    body: JSON.stringify({ command: cmd, timeout: opts.timeout ?? 120 }),
  });
}

export async function getResult(taskId: string): Promise<Outcome> {
  return jsonBody<Outcome>(`/tasks/${encodeURIComponent(taskId)}/result`);
}

export interface ResultsFilter {
  limit?: number;
  offset?: number;
  plan_id?: string;
  label?: string;
  q?: string;
}
export async function listResults(opts: ResultsFilter = {}): Promise<Paged<ResultRow>> {
  const params = new URLSearchParams({
    limit: String(opts.limit ?? 25),
    offset: String(opts.offset ?? 0),
  });
  if (opts.plan_id) params.set("plan_id", opts.plan_id);
  if (opts.label) params.set("label", opts.label);
  if (opts.q) params.set("q", opts.q);
  return jsonBody<Paged<ResultRow>>(`/results?${params}`);
}

export async function exportResults(opts: { plan_id?: string; label?: string } = {}): Promise<string> {
  const params = new URLSearchParams();
  if (opts.plan_id) params.set("plan_id", opts.plan_id);
  if (opts.label) params.set("label", opts.label);
  const res = await fetch(`${BASE}/results/export?${params}`);
  return res.text();
}

export async function classifyLog(text: string): Promise<ClassifyResult> {
  return jsonBody<ClassifyResult>("/classify", { method: "POST", body: JSON.stringify({ text }) });
}

export async function classifyMetrics(): Promise<Metrics> {
  return jsonBody<Metrics>("/classify/metrics");
}

export async function health(): Promise<{ status: string; version: string; db: string }> {
  return jsonBody<{ status: string; version: string; db: string }>("/health");
}

export const DEMO_COMMAND = "printf '# pass 4\\n# fail 0\\n# duration_ms 1\\n'";