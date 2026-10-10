import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Job, Project } from "../../api";
import { useGeneration } from "./useGeneration";

const project: Project = {
  id: "p1", created_at: "2026-10-10T00:00:00Z", active_leaf_id: null,
  fork_image_id: null, images: [], unfinished_requests: [],
};
const queued: Job = {
  id: "j1", project_id: "p1", request_id: "r1", state: "queued",
  width: 1024, height: 1024, step: null, total: null, image_id: null, error_code: null,
};
const success = (value: unknown) => ({ ok: true, value });
const failure = { ok: false, error: { code: "DATABASE_FAILED", message: "private detail" } };

function setup() {
  const callbacks = { onProject: vi.fn(), onError: vi.fn(), onComplete: vi.fn() };
  const api = {
    submit_request: vi.fn().mockResolvedValue(success(queued)),
    get_project: vi.fn().mockResolvedValue(success(project)),
    get_job: vi.fn().mockResolvedValue(success(queued)),
    cancel_job: vi.fn().mockResolvedValue(success(undefined)),
  };
  window.pywebview = { api };
  return { ...renderHook(() => useGeneration(callbacks)), api, callbacks };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it("keeps observing an accepted job when the initial conversation refresh fails", async () => {
  const { result, api, callbacks } = setup();
  api.get_project.mockResolvedValueOnce(failure);

  await act(async () => { await result.current.startGeneration("submit_request", "p1", "forest"); });

  expect(result.current.job?.id).toBe("j1");
  expect(callbacks.onError).toHaveBeenCalledWith(expect.objectContaining({ code: "DATABASE_FAILED" }));
  api.get_job.mockResolvedValue(success({ ...queued, state: "completed" }));
  await act(async () => { await vi.advanceTimersToNextTimerAsync(); });
  expect(result.current.job).toBeNull();
  expect(callbacks.onProject).toHaveBeenCalledWith(project);
  expect(callbacks.onComplete).toHaveBeenCalledOnce();
  expect(api.submit_request).toHaveBeenCalledOnce();
});

it("retries a completed job's conversation refresh before enabling another generation", async () => {
  const { result, api, callbacks } = setup();
  api.get_job.mockResolvedValue(success({ ...queued, state: "completed" }));
  api.get_project.mockResolvedValueOnce(success(project)).mockResolvedValueOnce(failure);

  await act(async () => { await result.current.startGeneration("submit_request", "p1", "forest"); });

  expect(result.current.job?.id).toBe("j1");
  expect(callbacks.onComplete).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersToNextTimerAsync(); });
  expect(result.current.job).toBeNull();
  expect(callbacks.onComplete).toHaveBeenCalledOnce();
});

it("allows cancellation to be retried when the bridge rejects it", async () => {
  const { result, api, callbacks } = setup();
  await act(async () => { await result.current.startGeneration("submit_request", "p1", "forest"); });
  api.cancel_job.mockResolvedValueOnce(failure);

  await act(async () => { result.current.cancelGeneration(); });

  expect(result.current.stopping).toBe(false);
  expect(result.current.job?.id).toBe("j1");
  expect(callbacks.onError).toHaveBeenCalledWith(expect.objectContaining({ code: "DATABASE_FAILED" }));
  await act(async () => { result.current.cancelGeneration(); });
  expect(api.cancel_job).toHaveBeenCalledTimes(2);
  expect(api.cancel_job).toHaveBeenLastCalledWith("j1");
  expect(result.current.stopping).toBe(true);
});

it("ignores pending progress after unmounting and stops scheduling polls", async () => {
  const { result, api, callbacks, unmount } = setup();
  let finish!: (value: unknown) => void;
  api.get_job.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  await act(async () => { await result.current.startGeneration("submit_request", "p1", "forest"); });
  callbacks.onProject.mockClear();

  unmount();
  await act(async () => { finish(success({ ...queued, state: "completed" })); });

  expect(callbacks.onProject).not.toHaveBeenCalled();
  expect(callbacks.onComplete).not.toHaveBeenCalled();
  api.get_job.mockClear();
  await act(async () => { await vi.runOnlyPendingTimersAsync(); });
  expect(api.get_job).not.toHaveBeenCalled();
});
