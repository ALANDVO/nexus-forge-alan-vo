import { beforeAll, describe, expect, it, vi } from "vitest";
import { createPlan, listPlans, HttpError } from "../src/api";

const PLAN_PAYLOAD = { id: "x", name: "n", status: "draft", task_count: 0, created_at: null, updated_at: null };

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("typed API client", () => {
  const fetch = vi.hoisted(() => vi.fn());
  beforeAll(() => vi.stubGlobal("fetch", fetch));

  it("createPlan returns a Plan on 201", async () => {
    fetch.mockResolvedValue(json(PLAN_PAYLOAD, 201));
    const p = await createPlan("n", "- [ ] a");
    expect(p.id).toBe("x");
    expect(p.name).toBe("n");
    expect(fetch).toHaveBeenCalledWith("/plans", expect.objectContaining({ method: "POST" }));
  });

  it("createPlan throws HttpError on 422", async () => {
    fetch.mockResolvedValue(
      json({ detail: [{ loc: ["body", "name"], msg: "field required" }] }, 422)
    );
    await expect(createPlan("", "- [ ] a")).rejects.toMatchObject({
      status: 422,
      name: "HttpError",
    });
  });

  it("listPlans maps the paged envelope", async () => {
    fetch.mockResolvedValue(
      json({
        items: [{ id: "1", name: "a", status: "draft", task_count: 1, created_at: "2026-01-01T00:00:00Z", updated_at: null }],
        total: 1,
        limit: 25,
        offset: 0,
      })
    );
    const r = await listPlans();
    expect(r.total).toBe(1);
    expect(r.items[0].id).toBe("1");
  });

  it("HttpError carries status and detail", () => {
    const err = new HttpError(400, "bad request");
    expect(err.status).toBe(400);
    expect(err.detail).toBe("bad request");
  });
});