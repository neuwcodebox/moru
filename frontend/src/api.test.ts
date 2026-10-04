import { afterEach, expect, it, vi } from "vitest";
import { BridgeError, call } from "./api";

afterEach(() => {
  delete window.pywebview;
});

it("retains the boundary error code without using server display text", async () => {
  window.pywebview = {
    api: { update_settings: vi.fn().mockResolvedValue({
      ok: false, error: { code: "INVALID_SETTINGS", message: "생성 설정을 확인해 주세요." },
    }) },
  };
  await expect(call("update_settings", {})).rejects.toMatchObject({
    name: "BridgeError", code: "INVALID_SETTINGS",
  });
});

it("reports a disconnected desktop with a translatable error code", async () => {
  await expect(call("bootstrap")).rejects.toEqual(new BridgeError("DESKTOP_UNAVAILABLE"));
});

it("hides unexpected bridge rejection details behind a stable code", async () => {
  window.pywebview = {
    api: { bootstrap: vi.fn().mockRejectedValue(new Error("private implementation path")) },
  };
  await expect(call("bootstrap")).rejects.toEqual(new BridgeError("BRIDGE_FAILED"));
});

it("does not alter successfully returned content", async () => {
  const value = { prompt: "silver-haired girl, daytime", language: "en" };
  window.pywebview = { api: { bootstrap: vi.fn().mockResolvedValue({ ok: true, value }) } };
  await expect(call("bootstrap")).resolves.toBe(value);
});

it.each([null, undefined, {}, { ok: false }, { ok: false, error: {} }])(
  "reports a malformed bridge response with a translatable code: %s",
  async (result) => {
    window.pywebview = { api: { bootstrap: vi.fn().mockResolvedValue(result) } };
    await expect(call("bootstrap")).rejects.toEqual(new BridgeError("BRIDGE_FAILED"));
  },
);
