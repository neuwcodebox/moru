import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import ModelsDialog from "./ModelsDialog";

it("offers local selection and download for a missing model without exposing backend paths", async () => {
  const user = userEvent.setup();
  const models = [{ id: "prompt", available: false }];
  const status = vi.fn(async () => ({ ok: true as const, value: models }));
  const select = vi.fn(async () => ({
    ok: true as const,
    value: [{ id: "prompt", available: true, filename: "custom-qwen.gguf" }],
  }));
  window.pywebview = {
    api: { get_model_status: status, select_local_model: select },
  };
  render(
    <ModelsDialog initial={models} onUpdate={vi.fn()} onClose={vi.fn()} />,
  );
  await screen.findByText("프롬프트 작성 모델");
  await user.click(screen.getByText("파일 선택"));
  expect(select).toHaveBeenCalledWith("prompt");
  expect(await screen.findByText("준비됨")).toBeTruthy();
  expect(screen.getByText("custom-qwen.gguf")).toBeTruthy();
  expect(screen.getByRole("dialog", { name: "모델 설정" })).toBeTruthy();
  expect(screen.queryByText("다운로드")).toBeNull();
});

it("displays byte progress and supports cancellation of an active download", async () => {
  const user = userEvent.setup();
  const models = [
    {
      id: "prompt",
      available: false,
      download: {
        model_id: "prompt",
        state: "downloading",
        received: 50,
        total: 100,
        error_code: null,
      },
    },
  ];
  const cancel = vi.fn(async () => ({ ok: true as const, value: models }));
  window.pywebview = {
    api: {
      get_model_status: vi.fn(async () => ({
        ok: true as const,
        value: models,
      })),
      cancel_model_download: cancel,
    },
  };
  render(
    <ModelsDialog initial={models} onUpdate={vi.fn()} onClose={vi.fn()} />,
  );
  expect(await screen.findByText("50%")).toBeTruthy();
  await user.click(screen.getByText("취소"));
  expect(cancel).toHaveBeenCalledWith("prompt");
});
