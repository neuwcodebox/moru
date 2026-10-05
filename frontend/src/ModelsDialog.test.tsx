import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import ModelsDialog from "./ModelsDialog";

it.each([
  ["ko", false], ["ko", true], ["en", false], ["en", true],
] as const)("offers browser download and local selection in %s (failed: %s)", async (language, failed) => {
  const { default: i18n } = await import("./i18n");
  await i18n.changeLanguage(language);
  const user = userEvent.setup();
  const filename = "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf";
  const url = `https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/blob/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e/${filename}`;
  let models = [{
    id: "prompt", available: false, filename: null as string | null,
    manual_download: { url, filename },
    download: failed ? {
      model_id: "prompt", state: "failed", received: 0, total: 100,
      error_code: "MODEL_DOWNLOAD_FAILED",
    } : null,
  }];
  const select = vi.fn(async () => {
    models = [{ ...models[0], available: true, filename, download: null }];
    return { ok: true as const, value: models };
  });
  window.pywebview = { api: {
    get_model_status: vi.fn(async () => ({ ok: true as const, value: models })),
    select_local_model: select,
  } };
  render(<ModelsDialog initial={models} onUpdate={vi.fn()} onClose={vi.fn()} />);
  const summary = screen.getByText(language === "ko" ? "직접 다운로드 하기" : "Manual download");
  const details = summary.closest("details")!;
  expect(details.open).toBe(failed);
  if (!failed) await user.click(summary);
  const link = screen.getByRole("link", { name: language === "ko" ? "Hugging Face에서 파일 받기" : "Download file on Hugging Face" });
  expect(link.getAttribute("href")).toBe(url);
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  expect(screen.getByText(filename)).toBeTruthy();
  expect(screen.getByText(language === "ko"
    ? "파일 페이지의 다운로드 버튼으로 아래 파일을 받으세요. 다운로드가 끝나면 이 모델의 ‘파일 선택’에서 받은 파일을 선택하세요."
    : "Use the download button on the file page to save the file below. Then use this model’s ‘Select file’ button to choose the downloaded file.")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: language === "ko" ? "파일 선택" : "Select file" }));
  expect(select).toHaveBeenCalledWith("prompt");
  expect(await screen.findByText(language === "ko" ? "준비됨" : "Ready")).toBeTruthy();
  expect(screen.queryByRole("link")).toBeNull();
});

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

it("shows English model roles, progress and download errors without changing filenames", async () => {
  const { default: i18n } = await import("./i18n");
  await i18n.changeLanguage("en");
  const models = [
    { id: "prompt", available: false, filename: "사용자-model.gguf", download: {
      model_id: "prompt", state: "downloading", received: 50, total: 100, error_code: null,
    } },
    { id: "vae", available: false, download: {
      model_id: "vae", state: "failed", received: 0, total: 100,
      error_code: "MODEL_CHECKSUM_FAILED", message: "이전 언어 메시지",
    } },
  ];
  window.pywebview = { api: { get_model_status: vi.fn(async () => ({ ok: true as const, value: models })) } };
  render(<ModelsDialog initial={models} onUpdate={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByRole("dialog", { name: "Model setup" })).toBeTruthy();
  expect(screen.getByRole("progressbar", { name: "Prompt-writing model download progress" })).toBeTruthy();
  expect(screen.getByText("사용자-model.gguf")).toBeTruthy();
  expect(screen.getByText("Image-decoding model")).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain("verification");
  expect(screen.queryByText("이전 언어 메시지")).toBeNull();
});
