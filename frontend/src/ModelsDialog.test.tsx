import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import ModelsDialog from "./ModelsDialog";
import type { ModelStatus } from "./api";
import { imageModels, generationSettings } from "./modelFixtures";

const preparedModels = ["prompt", "anima-turbo-v1.1", "text_encoder", "vae"].map((id) => ({
  id, available: true, filename: `${id}.safetensors`,
}));

function setupPreparation(models: ModelStatus[] = preparedModels) {
  window.pywebview = { api: {
    get_model_status: vi.fn(async () => ({ ok: true as const, value: models })),
  } };
  const onClose = vi.fn();
  render(<ModelsDialog initial={models} imageModels={imageModels} initialModelId={generationSettings.model_id}
    onUpdate={vi.fn()} onClose={onClose} />);
  return { onClose };
}

function renderModels(models: ModelStatus[]) {
  return render(<ModelsDialog initial={models} imageModels={imageModels} initialModelId={generationSettings.model_id}
    onUpdate={vi.fn()} onClose={vi.fn()} />);
}
function promptSection(language = "ko") {
  return within(screen.getByRole("region", { name: language === "ko" ? "프롬프트 작성 모델" : "Prompt-writing model" }));
}

it.each(["ko", "en"])("presents the prompt model with one heading in %s", async (language) => {
  const { default: i18n } = await import("./i18n");
  await i18n.changeLanguage(language);
  setupPreparation();
  const name = language === "ko" ? "프롬프트 작성 모델" : "Prompt-writing model";
  expect(promptSection(language).getByRole("heading", { name })).toBeTruthy();
  expect(screen.queryByText(language === "ko" ? "프롬프트 작성" : "Prompt writing")).toBeNull();
  expect(promptSection(language).getByText("prompt.safetensors")).toBeTruthy();
  expect(promptSection(language).getByText(language === "ko" ? "준비됨" : "Ready")).toBeTruthy();
});

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
  renderModels(models);
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
  await user.click(promptSection(language).getByRole("button", { name: language === "ko" ? "파일 선택" : "Select file" }));
  expect(select).toHaveBeenCalledWith("prompt");
  expect(await promptSection(language).findByText(language === "ko" ? "준비됨" : "Ready")).toBeTruthy();
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
  renderModels(models);
  await screen.findByText("프롬프트 작성 모델");
  await user.click(promptSection().getByText("파일 선택"));
  expect(select).toHaveBeenCalledWith("prompt");
  expect(await promptSection().findByText("준비됨")).toBeTruthy();
  expect(screen.getByText("custom-qwen.gguf")).toBeTruthy();
  expect(screen.getByRole("dialog", { name: "모델 준비" })).toBeTruthy();
  expect(promptSection().queryByText("다운로드")).toBeNull();
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
  renderModels(models);
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
  renderModels(models);
  expect(screen.getByRole("dialog", { name: "Model setup" })).toBeTruthy();
  expect(screen.getByRole("progressbar", { name: "Prompt-writing model download progress" })).toBeTruthy();
  expect(screen.getByText("사용자-model.gguf")).toBeTruthy();
  expect(screen.getByText("Image-decoding model")).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain("verification");
  expect(screen.queryByText("이전 언어 메시지")).toBeNull();
});

it("requires only the selected Anima variant and shared files", () => {
  setupPreparation();
  const imageSetup = within(screen.getByRole("region", { name: "이미지 생성 모델" }));
  expect(imageSetup.getByText("Anima Turbo")).toBeTruthy();
  expect(imageSetup.queryByText("Anima Aesthetic")).toBeNull();
  expect(imageSetup.getByRole("status").textContent).toBe("모델 파일이 모두 준비되었습니다.");
  expect(imageSetup.getByText("문장 이해 모델")).toBeTruthy();
  expect(imageSetup.getByText("이미지 복원 모델")).toBeTruthy();
});

it("offers only supported models for file preparation", () => {
  setupPreparation();
  const families = within(screen.getByLabelText("모델"));
  expect(families.getAllByRole("option").map((option) => option.textContent)).toEqual(["Anima"]);
  expect(screen.queryByRole("option", { name: /SDXL/ })).toBeNull();
});

it.each(["text_encoder", "vae"])("reports the selected model as unprepared when %s is missing", (missing) => {
  setupPreparation(preparedModels.filter((model) => model.id !== missing));
  expect(screen.getByRole("status").textContent).toBe("필요한 모델 파일을 준비하세요.");
});

it("browses another variant's files without offering generation settings or saving", async () => {
  setupPreparation();
  await userEvent.setup().selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
  expect(screen.getByText("Anima Aesthetic")).toBeTruthy();
  expect(screen.queryByText("Anima Turbo")).toBeNull();
  expect(screen.getByRole("status").textContent).toBe("필요한 모델 파일을 준비하세요.");
  expect(screen.queryByRole("button", { name: "저장" })).toBeNull();
  expect(screen.queryByText(/권장 생성 단계/)).toBeNull();
  expect(screen.queryByText(/추론 호환성/)).toBeNull();
});

it("closes after browsing another model's preparation files", async () => {
  const { onClose } = setupPreparation();
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
  await user.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledOnce();
});

it("reports a file preparation failure while keeping the dialog open", async () => {
  const { onClose } = setupPreparation();
  window.pywebview!.api.download_model = vi.fn(async () => ({
    ok: false as const, error: { code: "MODEL_DOWNLOAD_FAILED", message: "Download failed" },
  }));
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
  await user.click(screen.getByRole("button", { name: "다운로드" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(onClose).not.toHaveBeenCalled();
});

it("keeps an active download visible and cancellable after choosing another variant", async () => {
  const models = preparedModels.map((model) => model.id !== "anima-turbo-v1.1" ? model : {
    ...model, available: false, download: {
      model_id: model.id, state: "downloading", received: 50, total: 100, error_code: null,
    },
  });
  setupPreparation(models);
  const cancel = vi.fn(async () => ({ ok: true as const, value: preparedModels }));
  window.pywebview!.api.cancel_model_download = cancel;
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
  const downloads = within(screen.getByRole("region", { name: "다른 모델의 다운로드" }));
  expect(downloads.getByText("50%")).toBeTruthy();
  await user.click(downloads.getByRole("button", { name: "취소" }));
  expect(cancel).toHaveBeenCalledWith("anima-turbo-v1.1");
});
