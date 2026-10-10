import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import ChatGPTPromptOptions from "./ChatGPTPromptOptions";
import type { PromptSettings } from "./api";

const settings: PromptSettings = {
  context_size: 4096, max_tokens: 2048, thinking: true, history_turns: 4,
  reasoning_level: "low", provider: "chatgpt", chatgpt_model: "gpt-6-astra",
};

beforeEach(() => {
  window.pywebview = { api: { get_chatgpt_reasoning_efforts: vi.fn(async () => ({
    ok: true as const, value: ["low", "medium", "high", "xhigh", "max"],
  })) } };
});

function Options() {
  const [draft, setDraft] = useState(settings);
  return <ChatGPTPromptOptions settings={draft} onChange={setDraft} />;
}

it("offers only supported GPT effort levels", async () => {
  render(<Options />);
  const reasoning = screen.getByLabelText("추론 수준");
  await waitFor(() => expect(reasoning).toHaveProperty("disabled", false));
  expect(within(reasoning).getAllByRole("option").map((option) => option.getAttribute("value")))
    .toEqual(["default", "low", "medium", "high", "xhigh", "max"]);
  expect(reasoning).toHaveProperty("value", "default");
  fireEvent.change(reasoning, { target: { value: "high" } });
  expect(reasoning).toHaveProperty("value", "high");
  expect(screen.queryByLabelText("추론 사용")).toBeNull();
});

it("retains unsupported saved effort instead of silently replacing it", async () => {
  render(<ChatGPTPromptOptions settings={{ ...settings, chatgpt_reasoning_effort: "none" }}
    onChange={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent",
    "이 모델에서 지원하지 않는 추론 수준입니다. 모델 기본값이나 지원하는 수준을 선택하세요.");
  expect(screen.getByLabelText("추론 수준")).toHaveProperty("value", "none");
});

it("keeps only the model default when an account model has no documented choices", async () => {
  window.pywebview!.api.get_chatgpt_reasoning_efforts = vi.fn(async () => ({ ok: true as const, value: [] }));
  render(<Options />);
  await waitFor(() => expect(screen.getByLabelText("추론 수준")).toHaveProperty("disabled", false));
  expect(within(screen.getByLabelText("추론 수준")).getAllByRole("option")).toHaveLength(1);
});


it("shows a choices lookup failure without overwriting the saved effort", async () => {
  window.pywebview!.api.get_chatgpt_reasoning_efforts = vi.fn(async () => ({
    ok: false as const, error: { code: "CHATGPT_UNAVAILABLE", message: "unavailable" },
  }));
  const onChange = vi.fn();
  render(<ChatGPTPromptOptions settings={{ ...settings, chatgpt_reasoning_effort: "high" }}
    onChange={onChange} />);
  expect(await screen.findByText("ChatGPT에 연결할 수 없습니다. 연결을 확인하고 다시 시도해 주세요.")).toBeTruthy();
  expect(screen.getByLabelText("추론 수준")).toHaveProperty("value", "high");
  expect(onChange).not.toHaveBeenCalled();
});
