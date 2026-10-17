import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PlanDashboard } from "../src/components/PlanDashboard";

const METRICS = {
  accuracy: 1, precision: 1, recall: 1, f1: 1, train_size: 23, test_size: 10,
  tp: 6, fp: 0, tn: 4, fn: 0, dataset_size: 33, note: "labeled runner outputs",
};

function resp(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function planPage(items: unknown[]): Response {
  return resp({ items, total: items.length, limit: 25, offset: 0 });
}

describe("PlanDashboard", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
  afterEach(() => vi.restoreAllMocks());

  it("renders an empty state when the API returns no plans", async () => {
    const fetch = vi.mocked(globalThis.fetch);
    fetch.mockImplementation(async (input: RequestInfo | URL) => {
      const u = String(input);
      if (u.includes("/classify/metrics")) return resp(METRICS);
      if (u.startsWith("/plans")) return planPage([]);
      return new Response("", { status: 404 });
    });
    render(<PlanDashboard onView={() => {}} />);
    expect(await screen.findByText(/No plans yet/i)).toBeInTheDocument();
  });

  it("renders the plan list once it loads from the API", async () => {
    const fetch = vi.mocked(globalThis.fetch);
    fetch.mockImplementation(async (input: RequestInfo | URL) => {
      const u = String(input);
      if (u.includes("/classify/metrics")) return resp(METRICS);
      if (u.startsWith("/plans")) {
        return planPage([{
          id: "abc", name: "My Plan", status: "draft", task_count: 2,
          created_at: "2026-01-01T00:00:00Z", updated_at: null,
        }]);
      }
      return new Response("", { status: 404 });
    });
    render(<PlanDashboard onView={() => {}} />);
    expect(await screen.findByText("My Plan")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("submits the create form and refreshes the list", async () => {
    let created = false;
    const fetch = vi.mocked(globalThis.fetch);
    fetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const u = String(input);
      if (u.includes("/classify/metrics")) return resp(METRICS);
      if (u === "/plans" && init?.method === "POST") {
        created = true;
        return resp(
          { id: "n1", name: "New", status: "draft", task_count: 0, created_at: null, updated_at: null },
          201
        );
      }
      if (u.startsWith("/plans")) {
        return planPage(created
          ? [{ id: "n1", name: "New", status: "draft", task_count: 0, created_at: "2026-01-01T00:00:00Z", updated_at: null }]
          : []);
      }
      return new Response("", { status: 404 });
    });
    render(<PlanDashboard onView={() => {}} />);
    await screen.findByPlaceholderText("Plan name");
    fireEvent.change(screen.getByPlaceholderText("Plan name"), { target: { value: "New" } });
    fireEvent.change(screen.getByPlaceholderText(/task one/i), { target: { value: "- [ ] t" } });
    fireEvent.click(screen.getByRole("button", { name: /create plan/i }));
    expect(await screen.findByText("New")).toBeInTheDocument();
    expect(created).toBe(true);
  });
});