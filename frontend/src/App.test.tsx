import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Mock } from "vitest";
import App from "./App";
import { imageModels } from "./modelFixtures";
import Lightbox from "./Lightbox";
import type { Project, PromptSettings, Settings } from "./api";

const settings: Settings = {
  model_id: "anima-turbo-v1.1",
  width: 1024,
  height: 1024,
  steps: 10,
  cfg: 1,
  seed: null,
};
const promptSettings: PromptSettings = {
  context_size: 4096,
  max_tokens: 2048,
  thinking: true,
  history_turns: 4,
  reasoning_level: "medium",
};
const empty: Project = {
  id: "p1",
  created_at: "2026-10-04T08:00:00Z",
  active_leaf_id: null,
  fork_image_id: null,
  images: [],
  unfinished_requests: [],
};
const image = {
  id: "i1",
  width: 1024,
  height: 1024,
  request_text: "소녀를 그려줘",
  created_at: empty.created_at,
  parent_image_id: null,
  turn_id: "r1",
  versions: ["i1"],
};
const withImage: Project = { ...empty, active_leaf_id: "i1", images: [image] };
let current: Project;
let api: Record<string, Mock<(...args: any[]) => Promise<any>>>;
beforeEach(() => {
  current = structuredClone(empty);
  const success = (value: unknown) => Promise.resolve({ ok: true, value });
  api = {
    get_language: vi.fn(() => success("ko")),
    bootstrap: vi.fn(() =>
      success({
        language: "ko",
        project: current,
        projects: [empty],
        settings,
        image_models: imageModels,
        generation_defaults: {
          "anima-turbo-v1.1": { steps: 10, cfg: 1 },
          "anima-aesthetic-v1.1": { steps: 40, cfg: 4.5 },
        },
        prompt_settings: promptSettings,
      }),
    ),
    get_project: vi.fn(() => success(current)),
    get_model_status: vi.fn(() => success([])),
    list_projects: vi.fn(() => success([empty])),
    get_image_source: vi.fn(() => success("data:image/png;base64,abc")),
    submit_request: vi.fn(() => {
      current = withImage;
      return success({
        id: "j1",
        project_id: "p1",
        width: 1024, height: 1024, state: "queued",
        request_id: "r1",
      });
    }),
    get_job: vi.fn(() =>
      success({ id: "j1", project_id: "p1", width: 1024, height: 1024, state: "completed" }),
    ),
    cancel_job: vi.fn(() => success(undefined)),
    copy_prompt: vi.fn(() => success(undefined)),
    copy_image: vi.fn(() => success(undefined)),
    fork: vi.fn((_id, base) => {
      current = { ...current, id: "p2", fork_image_id: null };
      return success(current);
    }),
    get_image_details: vi.fn(() =>
      success({
        id: "i1",
        prompt: "private actual prompt",
        model_name: "Anima Turbo",
        settings: { ...settings, seed: "42" },
      }),
    ),
    generate_from_prompt: vi.fn(() =>
      success({ id: "j1", project_id: "p1", width: 1024, height: 1024, state: "queued" }),
    ),
    update_settings: vi.fn((values) => success(values)),
    get_chatgpt_reasoning_efforts: vi.fn(() => success(["low", "medium", "high"])),
    configure_prompt_writer: vi.fn(async (values) => {
      const result = await api.bootstrap();
      const saved = { ...result.value.prompt_settings, ...values };
      api.bootstrap.mockResolvedValue({ ...result, value: { ...result.value, prompt_settings: saved } });
      return { ok: true, value: saved };
    }),
    retry_request: vi.fn(() => {
      current = {
        ...current,
        unfinished_requests: current.unfinished_requests.map((request) => ({
          ...request,
          status: "pending",
          error_code: null,
          message: null,
        })),
      };
      return success({ id: "j1", project_id: "p1", width: 1024, height: 1024, state: "queued" });
    }),
    create_project: vi.fn(() => {
      current = { ...empty, id: "p2" };
      return success(current);
    }),
    select_version: vi.fn(() => success(current)),
    regenerate: vi.fn(() =>
      success({
        id: "j1",
        project_id: "p1",
        request_id: "r2",
        turn_id: "r1",
        width: 1024, height: 1024, state: "queued",
      }),
    ),
  };
  window.pywebview = { api };
});

it("prepares an inactive variant's file without changing the generation model", async () => {
  const user = userEvent.setup();
  let models = ["prompt", "anima-turbo-v1.1", "text_encoder", "vae"].map((id) => ({
    id, available: true, filename: id + ".safetensors",
  }));
  api.get_model_status.mockImplementation(async () => ({ ok: true, value: models }));
  api.select_local_model = vi.fn(async (id) => {
    models = [...models, { id, available: true, filename: "custom-aesthetic.safetensors" }];
    return { ok: true, value: models };
  });
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByRole("button", { name: "모델 준비" }));
  await user.selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
  const weights = within(screen.getByRole("group", { name: "Anima Aesthetic" }));
  await user.click(weights.getByRole("button", { name: "파일 선택" }));
  expect(api.select_local_model).toHaveBeenCalledWith("anima-aesthetic-v1.1");
  expect(await weights.findByText("custom-aesthetic.safetensors")).toBeTruthy();
  expect(api.update_settings).not.toHaveBeenCalled();
  expect(within(screen.getByRole("region", { name: "이미지 생성 모델" }))
    .queryByRole("button", { name: "저장" })).toBeNull();
  await user.keyboard("{Escape}");
  await user.click(screen.getByLabelText("생성 설정"));
  expect((screen.getByLabelText("버전") as HTMLSelectElement).value).toBe("anima-turbo-v1.1");
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("10");
  expect((screen.getByLabelText("프롬프트 반영 강도 (CFG)") as HTMLInputElement).value).toBe("1");
});

it("changes the active model only when generation settings are saved", async () => {
  const bootstrap = await api.bootstrap();
  const saved = { ...settings, steps: 12, cfg: 2, width: 832, height: 1216, seed: "42" };
  api.bootstrap.mockResolvedValue({ ...bootstrap, value: { ...bootstrap.value, settings: saved } });
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByRole("button", { name: "모델 준비" }));
  await user.selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
  await user.keyboard("{Escape}");
  expect(api.update_settings).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText("생성 설정"));
  expect((screen.getByLabelText("버전") as HTMLSelectElement).value).toBe(saved.model_id);
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("12");
  expect((screen.getByLabelText("프롬프트 반영 강도 (CFG)") as HTMLInputElement).value).toBe("2");
  expect((screen.getByLabelText("시드") as HTMLInputElement).value).toBe("42");
  await user.selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
  await user.click(screen.getByText("닫기", { selector: "button" }));
  expect(api.update_settings).toHaveBeenCalledWith(
    { ...saved, model_id: "anima-aesthetic-v1.1", steps: 40, cfg: 4.5 }, promptSettings,
  );
  await user.click(screen.getByRole("button", { name: "모델 준비" }));
  expect((screen.getByLabelText("버전") as HTMLSelectElement).value).toBe("anima-aesthetic-v1.1");
});

it("does not require the unselected variant at startup", async () => {
  const bootstrap = await api.bootstrap();
  api.bootstrap.mockResolvedValue({ ...bootstrap, value: { ...bootstrap.value,
    models: ["prompt", "anima-turbo-v1.1", "text_encoder", "vae"].map((id) => ({ id, available: true })),
  } });
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("restores Aesthetic without requiring Turbo weights", async () => {
  const bootstrap = await api.bootstrap();
  api.bootstrap.mockResolvedValue({ ...bootstrap, value: { ...bootstrap.value,
    settings: { ...settings, model_id: "anima-aesthetic-v1.1", steps: 40, cfg: 4.5 },
    models: ["prompt", "anima-aesthetic-v1.1", "text_encoder", "vae"].map((id) => ({ id, available: true })),
  } });
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  expect(screen.queryByRole("dialog")).toBeNull();
  await user.click(screen.getByLabelText("생성 설정"));
  expect((screen.getByLabelText("버전") as HTMLSelectElement).value).toBe("anima-aesthetic-v1.1");
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("40");
  expect(screen.queryByRole("option", { name: /SDXL/ })).toBeNull();
  await user.selectOptions(screen.getByLabelText("버전"), "anima-turbo-v1.1");
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("10");
});

it("shows only the moru wordmark beside the language selector in the header", async () => {
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  const header = screen.getByRole("banner");
  expect(within(header).getByText("moru")).toBeTruthy();
  expect(header.querySelector("img")).toBeNull();
  expect(within(header).getByRole("combobox", { name: "언어" })).toBeTruthy();
});

describe("conversation", () => {
  it("copies the selected image itself and confirms inside its button", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByRole("button", { name: "복사" }));
    expect(api.copy_image).toHaveBeenCalledWith("i1");
    expect(api.copy_prompt).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "복사 완료" })).toBeTruthy();
  });

  it("reveals a completed image's prompt on hover without fetching all prompts on startup", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    expect(api.get_image_details).not.toHaveBeenCalled();
    const image = screen.getByRole("button", { name: "이미지 전체 화면 보기" });
    await user.hover(image);
    expect(await within(image).findByText("private actual prompt")).toBeTruthy();
    expect(api.get_image_details).toHaveBeenCalledWith("i1");
    await user.unhover(image);
    expect(image.querySelector(".image-prompt-overlay")?.getAttribute("aria-hidden")).toBe("true");
    await user.hover(image);
    expect(api.get_image_details).toHaveBeenCalledOnce();
    await user.click(image);
    expect(screen.getByRole("dialog", { name: "이미지 보기" })).toBeTruthy();
  });

  it("shows a prompt-loading failure on the image cover", async () => {
    current = withImage;
    api.get_image_details.mockResolvedValue({ok: false, error: {code: "NOT_FOUND", message: "프롬프트 오류"}});
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.hover(screen.getByRole("button", { name: "이미지 전체 화면 보기" }));
    expect(await screen.findByText("작업 또는 이미지를 찾을 수 없습니다.")).toBeTruthy();
  });

  it.each([
    ["생성 설정", "생성 설정"],
    ["모델 준비", "모델 준비"],
    ["수정", "프롬프트"],
    ["이미지 전체 화면 보기", "이미지 보기"],
  ])("isolates all background controls while the %s dialog is open", async (button, title) => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByRole("button", { name: button }));
    await screen.findByRole("dialog", { name: title });
    const background = [
      document.querySelector("header")!,
      document.querySelector("main")!,
      document.querySelector("footer")!,
    ];
    expect(background.every((element) => element.hasAttribute("inert"))).toBe(true);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(background.every((element) => !element.hasAttribute("inert"))).toBe(true);
  });

  it("hides the prompt on opening the viewer and keeps it hidden after focus returns", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    const image = await screen.findByRole("button", { name: "이미지 전체 화면 보기" });
    await user.hover(image);
    await within(image).findByText("private actual prompt");
    await user.click(image);
    expect(image.querySelector(".image-prompt-overlay")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("main", { hidden: true }).hasAttribute("inert")).toBe(true);
    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(image);
    expect(image.querySelector(".image-prompt-overlay")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("main").hasAttribute("inert")).toBe(false);
    fireEvent.mouseEnter(image);
    expect(image.querySelector(".image-prompt-overlay")?.getAttribute("aria-hidden")).toBe("true");
    fireEvent.mouseMove(image);
    expect(image.querySelector(".image-prompt-overlay")?.getAttribute("aria-hidden")).toBe("false");
  });

  it("reveals prompts again on intentional keyboard focus after closing settings", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    const image = await screen.findByRole("button", { name: "이미지 전체 화면 보기" });
    await user.click(screen.getByLabelText("생성 설정"));
    await user.keyboard("{Escape}");
    for (let count = 0; count < 10 && document.activeElement !== image; count++)
      await user.tab({ shift: true });
    expect(document.activeElement).toBe(image);
    expect(image.querySelector(".image-prompt-overlay")?.getAttribute("aria-hidden")).toBe("false");
  });

  it("confirms successful branching into a new session and reports failures without success feedback", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("분기"));
    expect(await screen.findByText("선택한 이미지까지 새 작업으로 분기했습니다.")).toBeTruthy();
    await user.click(screen.getByLabelText("알림 닫기"));
    api.fork.mockResolvedValue({ok: false, error: {code: "DATABASE_FAILED", message: "분기 오류"}});
    await user.click(screen.getByText("분기"));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("작업 기록을 저장하거나 불러올 수 없습니다."));
    expect(screen.queryByText("선택한 이미지까지 새 작업으로 분기했습니다.")).toBeNull();
  });

  it("navigates history and versions with arrows in both the conversation and zoomed viewer", async () => {
    current = {
      ...empty, active_leaf_id: "i3",
      images: [
        {...image, id: "i1", turn_id: "r1", request_text: "첫 이미지", versions: ["i1", "i1b"]},
        {...image, id: "i2", turn_id: "r2", request_text: "둘째 이미지", versions: ["i2", "i2b"]},
        {...image, id: "i3", turn_id: "r3", request_text: "셋째 이미지", versions: ["i3"]},
      ],
    };
    api.get_image_source.mockImplementation(async (id) => ({ok: true, value: `data:image/png;base64,${id}`}));
    api.select_version.mockImplementation(async (_project, id) => {
      current = {...current, active_leaf_id: id, images: current.images.map(image =>
        image.versions.includes(id) ? {...image, id} : image)};
      return {ok: true, value: current};
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findAllByAltText("생성 이미지");
    const selectedText = () => document.querySelector(".turn.is-selected .user-message")?.textContent;
    await user.keyboard("{ArrowUp}");
    expect(selectedText()).toBe("둘째 이미지");
    await user.keyboard("{ArrowRight}");
    expect(api.select_version).toHaveBeenLastCalledWith("p1", "i2b");
    const secondTurn = document.querySelectorAll<HTMLElement>(".turn")[1];
    await waitFor(() => expect(secondTurn.querySelector("img")?.getAttribute("src")).toBe("data:image/png;base64,i2b"));
    await user.click(within(secondTurn).getByRole("button", {name: "이미지 전체 화면 보기"}));
    await waitFor(() => expect(screen.getByAltText("생성 이미지 전체 화면").getAttribute("src")).toBe("data:image/png;base64,i2b"));
    await user.click(screen.getByLabelText("확대"));
    expect(screen.getByText("125%")).toBeTruthy();
    expect(screen.getByAltText("생성 이미지 전체 화면").getAttribute("src")).toBe("data:image/png;base64,i2b");
    await user.keyboard("{ArrowLeft}");
    await waitFor(() => expect(screen.getByAltText("생성 이미지 전체 화면").getAttribute("src")).toBe("data:image/png;base64,i2"));
    expect(screen.getByText("100%")).toBeTruthy();
    await user.keyboard("{ArrowUp}");
    expect(selectedText()).toBe("첫 이미지");
    await user.keyboard("{ArrowUp}");
    expect(selectedText()).toBe("첫 이미지");
    await user.keyboard("{ArrowLeft}");
    expect(api.select_version).toHaveBeenLastCalledWith("p1", "i1b");
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");
    expect(selectedText()).toBe("셋째 이미지");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("preserves text editing and IME composition while supporting arrows in an empty composer", async () => {
    current = {...withImage, images: [image, {...image, id: "i2", turn_id: "r2", versions: ["i2"]}]};
    const user = userEvent.setup();
    render(<App />);
    await screen.findAllByAltText("생성 이미지");
    const input = screen.getByLabelText("이미지 요청");
    await user.type(input, "입력 중");
    await user.keyboard("{ArrowUp}");
    expect(document.querySelectorAll(".turn")[1].classList.contains("is-selected")).toBe(true);
    await user.clear(input);
    fireEvent.keyDown(input, {key: "ArrowUp", isComposing: true});
    expect(document.querySelectorAll(".turn")[1].classList.contains("is-selected")).toBe(true);
    await user.keyboard("{ArrowUp}");
    expect(document.querySelectorAll(".turn")[0].classList.contains("is-selected")).toBe(true);
  });

  it("returns focus to the image reached in the viewer when closing it", async () => {
    current = {...withImage, images: [image, {...image, id: "i2", turn_id: "r2", versions: ["i2"]}]};
    const user = userEvent.setup();
    render(<App />);
    await screen.findAllByAltText("생성 이미지");
    await user.click(screen.getAllByRole("button", {name: "이미지 전체 화면 보기"})[0]);
    await user.keyboard("{ArrowDown}{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    const second = document.querySelectorAll(".turn")[1];
    expect(second.classList.contains("is-selected")).toBe(true);
    expect(document.activeElement).toBe(within(second as HTMLElement).getByRole("button", {name: "이미지 전체 화면 보기"}));
  });

  it("keeps image navigation inactive in settings dialogs", async () => {
    current = {...withImage, images: [image, {...image, id: "i2", turn_id: "r2", versions: ["i2", "i2b"]}]};
    const user = userEvent.setup();
    render(<App />);
    await screen.findAllByAltText("생성 이미지");
    await user.click(screen.getByLabelText("생성 설정"));
    fireEvent.keyDown(screen.getByRole("dialog"), {key: "ArrowUp"});
    fireEvent.keyDown(screen.getByRole("dialog"), {key: "ArrowRight"});
    expect(document.querySelectorAll(".turn")[1].classList.contains("is-selected")).toBe(true);
    expect(api.select_version).not.toHaveBeenCalled();
  });

  it("does not change image versions while generation is running", async () => {
    current = {...withImage, images: [{...image, versions: ["i1", "i1b"]}]};
    api.get_job.mockResolvedValue({ok: true, value: {
      id: "j1", project_id: "p1", request_id: "r2", turn_id: "r1", width: 1024, height: 1024, state: "generating",
    }});
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByRole("button", {name: "다시"}));
    await screen.findByRole("region", {name: "생성 진행"});
    fireEvent.keyDown(document, {key: "ArrowRight"});
    expect(api.select_version).not.toHaveBeenCalled();
  });

  it.each(["button", "enter"])("jumps to the bottom immediately on %s submission before the backend responds", async (method) => {
    current = withImage;
    let accept!: (value: unknown) => void;
    api.submit_request.mockImplementation(() => new Promise((resolve) => { accept = resolve; }));
    api.get_job.mockResolvedValue({ ok: true, value: {
      id: "j1", project_id: "p1", request_id: "r2", width: 1024, height: 1024, state: "prompting",
    } });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    const conversation = screen.getByLabelText("대화");
    const scrollTo = vi.fn((options: ScrollToOptions) => { conversation.scrollTop = options.top ?? 0; });
    Object.defineProperties(conversation, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 400 },
      scrollTo: { configurable: true, value: scrollTo },
    });
    conversation.scrollTop = 100;
    fireEvent.scroll(conversation);
    expect(screen.getByRole("button", { name: "맨 아래로" })).toBeTruthy();
    await user.type(screen.getByRole("textbox", { name: "이미지 요청" }), "rain");
    if (method === "button") await user.click(screen.getByRole("button", { name: "전송" }));
    else await user.keyboard("{Enter}");
    expect(scrollTo).toHaveBeenCalledExactlyOnceWith({ top: 1000, behavior: "instant" });
    expect(conversation.scrollTop).toBe(1000);
    expect(screen.queryByRole("button", { name: "맨 아래로" })).toBeNull();
    expect(api.get_job).not.toHaveBeenCalled();
    Object.defineProperty(conversation, "scrollHeight", { configurable: true, value: 1600 });
    await act(async () => accept({ ok: true, value: {
      id: "j1", project_id: "p1", request_id: "r2", width: 1024, height: 1024, state: "queued",
    } }));
    expect(conversation.scrollTop).toBe(1600);
  });

  it("keeps the reading position when generation updates arrive above the composer", async () => {
    current = withImage;
    api.get_job.mockResolvedValue({
      ok: true,
      value: {
        id: "j1",
        project_id: "p1",
        request_id: "r2",
        turn_id: "r1",
        width: 1024, height: 1024, state: "generating",
        prompt_text: "moonlit forest",
        step: 2,
        total: 10,
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    const conversation = screen.getByLabelText("대화");
    Object.defineProperties(conversation, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 400 },
    });
    conversation.scrollTop = 100;
    fireEvent.scroll(conversation);
    await user.click(screen.getByRole("button", { name: "다시" }));
    await screen.findByText("moonlit forest");
    expect(conversation.scrollTop).toBe(100);
    expect(screen.getByRole("button", { name: "맨 아래로" })).toBeTruthy();
  });

  it("regenerates inside the existing image turn and keeps live text in its placeholder", async () => {
    current = withImage;
    api.get_job.mockResolvedValue({
      ok: true,
      value: {
        id: "j1",
        project_id: "p1",
        request_id: "r2",
        turn_id: "r1",
        width: 1024, height: 1024, state: "generating",
        step: 1,
        total: 10,
        prompt_text: "forest, moonlight",
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByRole("button", { name: "다시" }));
    expect(api.regenerate).toHaveBeenCalledWith("i1");
    const progress = await screen.findByRole("region", { name: "생성 진행" });
    expect(screen.getAllByText("소녀를 그려줘")).toHaveLength(1);
    expect(
      screen.getByLabelText("대화").querySelectorAll(".turn"),
    ).toHaveLength(1);
    expect(progress.closest(".turn")).toBeTruthy();
    expect(
      within(progress)
        .getByText("forest, moonlight")
        .closest(".generation-canvas"),
    ).toBeTruthy();
    expect(screen.queryByAltText("생성 이미지")).toBeNull();
  });

  it("shows a floating jump button only when scrolled away from the bottom", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    const conversation = screen.getByLabelText("대화");
    const scrollTo = vi.fn();
    Object.defineProperties(conversation, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 400 },
      scrollTo: { configurable: true, value: scrollTo },
    });
    expect(screen.queryByRole("button", { name: "맨 아래로" })).toBeNull();
    conversation.scrollTop = 100;
    fireEvent.scroll(conversation);
    await user.click(screen.getByRole("button", { name: "맨 아래로" }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: "instant" });
    expect(screen.queryByRole("button", { name: "맨 아래로" })).toBeNull();
    conversation.scrollTop = 600;
    fireEvent.scroll(conversation);
    expect(screen.queryByRole("button", { name: "맨 아래로" })).toBeNull();
  });

  it("opens the prompt of the currently selected image version", async () => {
    current = { ...withImage, images: [{ ...image, versions: ["i1", "i2"] }] };
    api.select_version.mockImplementation(() => {
      current = {
        ...current,
        active_leaf_id: "i2",
        images: [{ ...image, id: "i2", versions: ["i1", "i2"] }],
      };
      return Promise.resolve({ ok: true, value: current });
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("1 / 2");
    await user.click(screen.getByLabelText("다음 이미지"));
    await screen.findByText("2 / 2");
    await user.click(screen.getByRole("button", { name: "수정" }));
    expect(api.get_image_details).toHaveBeenCalledWith("i2");
    expect(
      screen.getByLabelText("대화").querySelectorAll(".turn"),
    ).toHaveLength(1);
  });

  it.each(["completed", "cancelled", "failed"])(
    "restores the send button after a %s job",
    async (state) => {
      const scheduled: (() => Promise<void>)[] = [];
      const realTimeout = globalThis.setTimeout;
      const timer = vi
        .spyOn(globalThis, "setTimeout")
        .mockImplementation((callback, delay, ...args) => {
          if (delay === 300 && typeof callback === "function") {
            scheduled.push(callback as () => Promise<void>);
            return 0 as unknown as ReturnType<typeof setTimeout>;
          }
          return realTimeout(callback, delay, ...args);
        });
      try {
        const user = userEvent.setup();
        api.get_job.mockResolvedValue({
          ok: true,
          value: {
            id: "j1",
            project_id: "p1",
            width: 1024, height: 1024, state: "generating",
            step: 3,
            total: 10,
          },
        });
        render(<App />);
        await screen.findByText("어떤 장면을 그릴까요?");
        await user.type(screen.getByLabelText("이미지 요청"), "풍경{Enter}");
        expect(screen.getByRole("button", { name: "중지" })).toBeTruthy();
        expect(screen.queryByRole("button", { name: "전송" })).toBeNull();
        if (state === "cancelled") {
          await user.click(screen.getByRole("button", { name: "중지" }));
          expect(api.cancel_job).toHaveBeenCalledWith("j1");
        }
        api.get_job.mockResolvedValue({
          ok: true,
          value: { id: "j1", project_id: "p1", state },
        });
        await act(async () => {
          await scheduled.shift()!();
        });
        expect(screen.queryByRole("button", { name: "중지" })).toBeNull();
        expect(screen.getByRole("button", { name: "전송" })).toBeTruthy();
        expect(screen.queryByRole("region", { name: "생성 진행" })).toBeNull();
      } finally {
        timer.mockRestore();
      }
    },
  );

  it("keeps model settings and history in the same header group when another project is added", async () => {
    const user = userEvent.setup();
    api.list_projects.mockImplementation(() =>
      Promise.resolve({ ok: true, value: [current, empty] }),
    );
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    const history = screen.getByRole("combobox", { name: "작업 기록" });
    const models = screen.getByRole("button", { name: "모델 준비" });
    expect(history.parentElement).toBe(models.parentElement);
    await user.click(screen.getByRole("button", { name: "새 작업" }));
    expect(screen.getByRole("combobox", { name: "작업 기록" })).toBe(history);
    expect(screen.getByRole("button", { name: "모델 준비" })).toBe(models);
    expect(within(history).getAllByRole("option")).toHaveLength(2);
  });

  it("keeps the stop button usable when cancellation fails", async () => {
    const user = userEvent.setup();
    api.get_job.mockResolvedValue({
      ok: true,
      value: { id: "j1", project_id: "p1", width: 1024, height: 1024, state: "loading_model" },
    });
    api.cancel_job.mockRejectedValue(new Error("중지 요청 실패"));
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.type(screen.getByLabelText("이미지 요청"), "풍경{Enter}");
    await user.click(screen.getByRole("button", { name: "중지" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "데스크톱 앱과 통신할 수 없습니다. 다시 시도해 주세요.",
    );
    expect(
      (screen.getByRole("button", { name: "중지" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    expect(screen.queryByRole("button", { name: "전송" })).toBeNull();
  });
  it("closes the manual prompt dialog when generation is accepted even if refreshing the conversation fails", async () => {
    current = withImage;
    api.get_project.mockRejectedValue(new Error("대화를 불러올 수 없습니다."));
    api.get_job.mockResolvedValue({
      ok: true,
      value: { id: "j1", project_id: "p1", width: 1024, height: 1024, state: "prompting" },
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("수정"));
    await user.click(screen.getByText("이 프롬프트로 생성"));
    await screen.findByText("프롬프트 작성 중…");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.generate_from_prompt).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert").textContent).toContain(
      "데스크톱 앱과 통신할 수 없습니다. 다시 시도해 주세요.",
    );
  });
  it("clears a failed request status as soon as its retry is accepted", async () => {
    current = {
      ...empty,
      unfinished_requests: [
        {
          id: "r1",
          text: "밤 풍경",
          status: "failed",
          error_code: "GENERATION_FAILED",
          message: "이미지 생성에 실패했습니다.",
          turn_id: null,
          width: 832,
          height: 1216,
        },
      ],
    };
    api.get_job.mockResolvedValue({
      ok: true,
      value: { id: "j1", project_id: "p1", width: 1024, height: 1024, state: "prompting" },
    });
    const user = userEvent.setup();
    render(<App />);
    const failure = await screen.findByRole("region", { name: "생성 실패" });
    expect(failure.style.aspectRatio).toBe("832 / 1216");
    expect(within(failure).getByRole("alert").textContent).toBe("이미지 생성에 실패했습니다. 다시 시도해 주세요.");
    await user.click(within(failure).getByRole("button", { name: "재시도" }));
    await screen.findByText("프롬프트 작성 중…");
    expect(screen.queryByText("이미지 생성에 실패했습니다. 다시 시도해 주세요.")).toBeNull();
    expect(api.retry_request).toHaveBeenCalledWith("r1");
  });
  it.each([
    ["PROMPT_LLM_FAILED", "프롬프트 준비에 실패했습니다. 다시 시도해 주세요."],
    ["PROMPT_EMPTY_RESPONSE", "프롬프트 모델이 최종 프롬프트를 반환하지 않았습니다. 다시 시도해 주세요."],
    ["PROMPT_INVALID_RESPONSE", "프롬프트 모델이 최종 프롬프트 대신 사고 과정을 반환했습니다. 다시 시도해 주세요."],
    ["PROMPT_NON_ENGLISH_RESPONSE", "생성된 프롬프트에 영어 외 문자가 포함되었습니다. 다시 시도해 주세요."],
    ["PROMPT_OUTPUT_TOO_LONG", "출력 토큰 한도에 도달해 프롬프트가 중단되었습니다. 재시도하거나 고급 설정에서 출력 한도를 늘리거나 추론 수준을 낮춰 주세요."],
    ["PROMPT_RESPONSE_INTERRUPTED", "프롬프트 모델의 응답이 완료되기 전에 중단되었습니다. 다시 시도해 주세요."],
    ["GENERATION_FAILED", "이미지 생성에 실패했습니다. 다시 시도해 주세요."],
  ])("shows %s inside the image placeholder without a footer error", async (code, message) => {
    api.submit_request.mockImplementation(() => {
      current = { ...empty, unfinished_requests: [{
        id: "r1", text: "밤 풍경", status: "failed", error_code: code,
        message: null, turn_id: null, width: 1216, height: 832,
      }] };
      return Promise.resolve({ ok: true, value: {
        id: "j1", project_id: "p1", request_id: "r1", state: "queued",
        width: 1216, height: 832,
      } });
    });
    api.get_job.mockResolvedValue({ ok: true, value: {
      id: "j1", project_id: "p1", request_id: "r1", state: "failed",
      width: 1216, height: 832, error_code: code,
    } });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.type(screen.getByLabelText("이미지 요청"), "밤 풍경{Enter}");
    const failure = await screen.findByRole("region", { name: "생성 실패" });
    expect(failure.style.aspectRatio).toBe("1216 / 832");
    expect(within(failure).getByRole("alert").textContent).toBe(message);
    expect(within(failure).getByRole("button", { name: "재시도" })).toBeTruthy();
    expect(screen.getAllByText(message)).toHaveLength(1);
    expect(document.querySelector("footer .error-banner")).toBeNull();
  });

  it("keeps stopped requests neutral and disables their retry while another job runs", async () => {
    current = { ...empty, unfinished_requests: [{
      id: "stopped", text: "중지한 풍경", status: "cancelled", error_code: "GENERATION_CANCELLED",
      message: null, turn_id: null, width: 832, height: 1216,
    }] };
    api.submit_request.mockResolvedValue({ ok: true, value: {
      id: "j1", project_id: "p1", request_id: "other", state: "queued",
      width: 1024, height: 1024,
    } });
    api.get_job.mockResolvedValue({ ok: true, value: {
      id: "j1", project_id: "p1", request_id: "other", state: "prompting",
      width: 1024, height: 1024,
    } });
    const user = userEvent.setup();
    render(<App />);
    const stopped = await screen.findByRole("region", { name: "생성 중지" });
    expect(stopped.classList.contains("is-cancelled")).toBe(true);
    expect(within(stopped).getByRole("status").textContent).toBe("생성이 취소되었습니다.");
    expect(within(stopped).queryByRole("alert")).toBeNull();
    await user.type(screen.getByLabelText("이미지 요청"), "다른 풍경{Enter}");
    await screen.findByRole("region", { name: "생성 진행" });
    expect((within(stopped).getByRole("button", { name: "재시도" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it.each(["regenerate", "generate_from_prompt"])(
    "keeps the previous image and puts a failed %s in a placeholder in the same turn",
    async (method) => {
      current = withImage;
      api[method].mockImplementation(() => {
        current = { ...withImage, unfinished_requests: [{
          id: "r2", text: null, status: "failed", error_code: "GENERATION_FAILED",
          message: null, turn_id: "r1", width: 832, height: 1216,
        }] };
        return Promise.resolve({ ok: true, value: {
          id: "j1", project_id: "p1", request_id: "r2", turn_id: "r1",
          state: "queued", width: 832, height: 1216,
        } });
      });
      api.get_job.mockResolvedValue({ ok: true, value: {
        id: "j1", project_id: "p1", request_id: "r2", turn_id: "r1",
        state: "failed", width: 832, height: 1216, error_code: "GENERATION_FAILED",
      } });
      const user = userEvent.setup();
      render(<App />);
      await screen.findByAltText("생성 이미지");
      if (method === "generate_from_prompt") {
        await user.click(screen.getByRole("button", { name: "수정" }));
        await user.click(await screen.findByRole("button", { name: "이 프롬프트로 생성" }));
      } else {
        await user.click(screen.getByRole("button", { name: "다시" }));
      }
      const failure = await screen.findByRole("region", { name: "생성 실패" });
      expect(failure.closest(".turn")).toBeTruthy();
      expect(failure.style.aspectRatio).toBe("832 / 1216");
      expect(screen.getByAltText("생성 이미지")).toBeTruthy();
      expect(document.querySelectorAll(".turn")).toHaveLength(1);
      expect(document.querySelector("footer .error-banner")).toBeNull();

      api.get_job.mockResolvedValue({ ok: true, value: {
        id: "j2", project_id: "p1", request_id: "r2", turn_id: "r1",
        state: "generating", width: 832, height: 1216,
      } });
      // A refresh can still contain the old failure after the retry was accepted.
      api.retry_request.mockResolvedValue({ ok: true, value: {
        id: "j2", project_id: "p1", request_id: "r2", turn_id: "r1",
        state: "queued", width: 832, height: 1216,
      } });
      await user.click(within(failure).getByRole("button", { name: "재시도" }));
      expect(api.retry_request).toHaveBeenCalledWith("r2");
      expect(await screen.findByRole("region", { name: "생성 진행" })).toBeTruthy();
      expect(screen.queryByRole("region", { name: "생성 실패" })).toBeNull();
    },
  );
  it("copies the edited prompt through the desktop clipboard bridge", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("수정"));
    const editor = screen.getByLabelText("실제 생성 프롬프트");
    await user.clear(editor);
    await user.type(editor, "edited image prompt");
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "복사" }),
    );
    expect(api.copy_prompt).toHaveBeenCalledWith("edited image prompt");
    expect(await screen.findByText("복사했습니다.")).toBeTruthy();
  });

  it("shows only thinking status and cancels with the composer stop button", async () => {
    const user = userEvent.setup();
    api.get_job.mockResolvedValue({
      ok: true,
      value: {
        id: "j1",
        project_id: "p1",
        width: 1024, height: 1024, state: "prompting",
        thinking_enabled: true,
        thinking_text: "Choosing the scene",
      },
    });
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.type(
      screen.getByLabelText("이미지 요청"),
      "소녀를 그려줘{Enter}",
    );
    const conversation = screen.getByRole("main", { name: "대화" });
    const thinking = await within(conversation).findByText("생각 중…");
    const status = thinking.closest('[aria-label="생성 진행"]') as HTMLElement;
    expect(screen.queryByText("프롬프트 준비")).toBeNull();
    expect(within(status).queryByText("Choosing the scene")).toBeNull();
    expect(screen.queryByText("생각 과정")).toBeNull();
    expect(screen.queryByText("취소")).toBeNull();
    expect(screen.queryByRole("button", { name: "전송" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "중지" }));
    expect(api.cancel_job).toHaveBeenCalledWith("j1");
  });

  it("sends natural language with Enter and displays the resulting image", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.type(
      screen.getByLabelText("이미지 요청"),
      "소녀를 그려줘{Enter}",
    );
    await screen.findByAltText("생성 이미지");
    expect(api.submit_request).toHaveBeenCalledWith("p1", "소녀를 그려줘");
    expect(screen.getByText("소녀를 그려줘")).toBeTruthy();
    expect(screen.queryByText("private actual prompt")).toBeNull();
  });

  it("inserts a newline with Shift+Enter and does not submit during IME composition", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    const input = screen.getByLabelText("이미지 요청");
    await user.type(input, "풍경{Shift>}{Enter}{/Shift}밤");
    expect((input as HTMLTextAreaElement).value).toBe("풍경\n밤");
    fireEvent.keyDown(input, { key: "Enter", isComposing: true, keyCode: 229 });
    expect(api.submit_request).not.toHaveBeenCalled();
  });

  it("copies a session immediately when the user forks an image", async () => {
    current = withImage;
    api.list_projects.mockImplementation(() =>
      Promise.resolve({ ok: true, value: [current, empty] }),
    );
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("분기"));
    expect(api.fork).toHaveBeenCalledWith("p1", "i1");
    expect(
      (screen.getByLabelText("작업 기록") as HTMLSelectElement).value,
    ).toBe("p2");
    expect(screen.queryByLabelText("분기 취소")).toBeNull();
  });

  it("exposes the prompt only in its dialog and submits manual edits as a Fork", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("수정"));
    const dialog = await screen.findByRole("dialog", { name: "프롬프트" });
    const prompt = within(dialog).getByLabelText("실제 생성 프롬프트");
    await user.clear(prompt);
    await user.type(prompt, "manually changed");
    await user.click(within(dialog).getByText("이 프롬프트로 생성"));
    expect(api.generate_from_prompt).toHaveBeenCalledWith(
      "i1",
      "manually changed",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("creates an empty project and clears the pending Fork", async () => {
    current = { ...withImage, fork_image_id: "i1" };
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("새 작업"));
    await screen.findByText("어떤 장면을 그릴까요?");
    expect(screen.queryByText("분기: #i1")).toBeNull();
    expect(api.create_project).toHaveBeenCalledOnce();
  });

  it("switches sibling branches from the branching image", async () => {
    current = {
      ...withImage,
      images: [
        image,
        {
          ...image,
          id: "i2",
          turn_id: "r2",
          parent_image_id: "i1",
          versions: ["i2", "i3"],
        },
      ],
    };
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("1 / 2");
    await user.click(screen.getByLabelText("다음 이미지"));
    expect(api.select_version).toHaveBeenCalledWith("p1", "i3");
  });

  it("saves a resolution preset and preserves a large seed as text", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.click(screen.getByLabelText("생성 설정"));
    await user.selectOptions(
      screen.getByLabelText("해상도 프리셋"),
      "832x1216",
    );
    await user.type(screen.getByLabelText("시드"), "9223372036854775807");
    await user.click(screen.getByText("닫기", { selector: "button" }));
    expect(api.update_settings).toHaveBeenCalledWith(
      {
        ...settings,
        width: 832,
        height: 1216,
        seed: "9223372036854775807",
      },
      promptSettings,
    );
  });

  it("saves advanced LLM settings and shows the saved values when reopened", async () => {
    const user = userEvent.setup();
    promptProviderBootstrap("local", true);
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 설정"));
    expect(screen.queryByRole("button", { name: "저장" })).toBeNull();
    const context = screen.getByLabelText("컨텍스트 크기");
    const output = screen.getByLabelText("출력 토큰 한도");
    const thinking = screen.getByLabelText("추론 사용") as HTMLInputElement;
    expect((context as HTMLInputElement).value).toBe("4096");
    expect((output as HTMLInputElement).value).toBe("2048");
    expect(thinking.checked).toBe(true);
    await user.clear(context);
    await user.type(context, "8192");
    await user.clear(output);
    await user.type(output, "4096");
    await user.click(thinking);
    await user.click(screen.getByText("닫기", { selector: "button" }));
    expect(api.update_settings).toHaveBeenCalledWith(settings, {
      ...promptSettings, provider: "local", chatgpt_model: "available-gpt",
      context_size: 8192,
      max_tokens: 4096,
      thinking: false,
      history_turns: 4,
      reasoning_level: "medium",
    });
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 설정"));
    expect(
      (screen.getByLabelText("컨텍스트 크기") as HTMLInputElement).value,
    ).toBe("8192");
    expect(
      (screen.getByLabelText("추론 사용") as HTMLInputElement).checked,
    ).toBe(false);
  });

  it("applies the chosen model's recommended sampling settings and saves custom overrides", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.click(screen.getByLabelText("생성 설정"));
    await user.selectOptions(screen.getByLabelText("버전"), "anima-aesthetic-v1.1");
    expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("40");
    expect((screen.getByLabelText("프롬프트 반영 강도 (CFG)") as HTMLInputElement).value).toBe("4.5");
    await user.clear(screen.getByLabelText("생성 단계"));
    await user.type(screen.getByLabelText("생성 단계"), "35");
    await user.click(screen.getByText("닫기", { selector: "button" }));
    expect(api.update_settings).toHaveBeenCalledWith(
      { ...settings, model_id: "anima-aesthetic-v1.1", steps: 35, cfg: 4.5 },
      promptSettings,
    );
    await user.click(screen.getByLabelText("생성 설정"));
    await user.selectOptions(screen.getByLabelText("버전"), "anima-turbo-v1.1");
    expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("10");
    expect((screen.getByLabelText("프롬프트 반영 강도 (CFG)") as HTMLInputElement).value).toBe("1");
  });

  it("defaults to medium reasoning and persists the chosen level while disabling it with thinking", async () => {
    const user = userEvent.setup();
    promptProviderBootstrap("local", true);
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 설정"));
    expect((screen.getByLabelText("추론 수준") as HTMLSelectElement).value).toBe("medium");
    expect(screen.getByRole("option", { name: "높음 · 추론 예산의 100%" })).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("추론 수준"), "high");
    await user.click(screen.getByLabelText("추론 사용"));
    expect((screen.getByLabelText("추론 수준") as HTMLSelectElement).disabled).toBe(true);
    await user.click(screen.getByText("닫기", { selector: "button" }));
    expect(api.update_settings).toHaveBeenCalledWith(settings, {
      ...promptSettings, provider: "local", chatgpt_model: "available-gpt",
      thinking: false, reasoning_level: "high",
    });
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 설정"));
    await user.click(screen.getByLabelText("추론 사용"));
    expect((screen.getByLabelText("추론 수준") as HTMLSelectElement).value).toBe("high");
    expect((screen.getByLabelText("추론 수준") as HTMLSelectElement).disabled).toBe(false);
  });

  it("keeps the dialog open without saving when output leaves no input context", async () => {
    const user = userEvent.setup();
    promptProviderBootstrap("local", true);
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 설정"));
    const output = screen.getByLabelText("출력 토큰 한도");
    await user.clear(output);
    await user.type(output, "8192");
    await user.click(screen.getByText("닫기", { selector: "button" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "출력 토큰 한도는 컨텍스트 크기보다 작아야 합니다.",
    );
    expect(api.update_settings).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "생성 설정" })).toBeTruthy();
  });
});

it("fits, zooms, and closes the fullscreen viewer with Escape", async () => {
  const user = userEvent.setup();
  const close = vi.fn();
  render(<Lightbox source="data:image/png;base64,abc" onClose={close} />);
  const dialog = screen.getByRole("dialog", { name: "이미지 보기" });
  expect(within(dialog).queryByRole("heading")).toBeNull();
  expect(screen.getByLabelText("확대").closest(".modal-header")).toBe(
    screen.getByLabelText("닫기").closest(".modal-header"),
  );
  expect(screen.getByText("100%")).toBeTruthy();
  await user.click(screen.getByLabelText("확대"));
  expect(screen.getByText("125%")).toBeTruthy();
  await user.click(screen.getByLabelText("화면 맞춤"));
  expect(screen.getByText("100%")).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(close).toHaveBeenCalledOnce();
});

it("pans the fullscreen image while dragging and resets its position when fitted", async () => {
  const user = userEvent.setup();
  render(<Lightbox source="data:image/png;base64,abc" onClose={vi.fn()} />);
  const image = screen.getByAltText("생성 이미지 전체 화면");
  const viewer = image.parentElement!;
  fireEvent(
    viewer,
    new MouseEvent("pointerdown", { bubbles: true, clientX: 10, clientY: 20 }),
  );
  fireEvent(
    viewer,
    new MouseEvent("pointermove", { bubbles: true, clientX: 40, clientY: 60 }),
  );
  expect(image.style.transform).toBe("translate(30px, 40px) scale(1)");
  fireEvent(viewer, new MouseEvent("pointerup", { bubbles: true }));
  fireEvent(
    viewer,
    new MouseEvent("pointermove", { bubbles: true, clientX: 80, clientY: 100 }),
  );
  expect(image.style.transform).toBe("translate(30px, 40px) scale(1)");
  await user.click(screen.getByLabelText("화면 맞춤"));
  expect(image.style.transform).toBe("translate(0px, 0px) scale(1)");
});

it("consumes viewer wheel gestures so they cannot scroll the background", () => {
  render(<Lightbox source="data:image/png;base64,abc" onClose={vi.fn()} />);
  const wheel = new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: -100 });
  const background = vi.fn();
  document.addEventListener("wheel", background);
  try {
    fireEvent(screen.getByAltText("생성 이미지 전체 화면"), wheel);
    expect(wheel.defaultPrevented).toBe(true);
    expect(background).not.toHaveBeenCalled();
    expect(screen.getByText("110%")).toBeTruthy();
  } finally {
    document.removeEventListener("wheel", background);
  }
});

it("waits for the pywebview ready event before loading state", async () => {
  const bridge = window.pywebview;
  delete window.pywebview;
  render(<App />);
  expect(api.bootstrap).not.toHaveBeenCalled();
  window.pywebview = bridge;
  await act(async () => window.dispatchEvent(new Event("pywebviewready")));
  expect(await screen.findByText("어떤 장면을 그릴까요?")).toBeTruthy();
});

const chatgptStatus = {
  connected: true, plan_enabled: true, active_account: "oaiapp_moru", email: "user@example.com",
  accounts: [{ id: "oaiapp_moru", email: "user@example.com", connected: true }],
  login_state: "idle", error_code: null, welcome_pending: false,
};

function promptProviderBootstrap(provider: "local" | "chatgpt", localReady: boolean) {
  api.get_model_status.mockResolvedValue({ ok: true, value: [
    { id: "prompt", available: localReady },
    ...imageModels[0].asset_ids.map((id) => ({ id, available: true })),
  ] });
  api.bootstrap.mockImplementation(async () => ({ ok: true, value: {
    language: "ko", project: current, projects: [empty], settings, image_models: imageModels,
    generation_defaults: {}, prompt_settings: { ...promptSettings, provider, chatgpt_model: "available-gpt" },
    models: [
      { id: "prompt", available: localReady },
      ...imageModels[0].asset_ids.map((id) => ({ id, available: true })),
    ],
    chatgpt: chatgptStatus,
  } }));
}

it("starts with ChatGPT and no GGUF without opening model setup", async () => {
  promptProviderBootstrap("chatgpt", false);
  render(<App />);
  await screen.findByRole("combobox", { name: "프롬프트 작성 모델" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect((screen.getByRole("combobox", { name: "프롬프트 작성 모델" }) as HTMLSelectElement).value)
    .toBe("chatgpt");
  fireEvent.change(screen.getByRole("textbox", { name: "이미지 요청" }), { target: { value: "girl" } });
  expect((screen.getByRole("button", { name: "전송" }) as HTMLButtonElement).disabled).toBe(false);
});

it("switches configured prompt providers beside the composer and saves the selection", async () => {
  const user = userEvent.setup();
  promptProviderBootstrap("local", true);
  api.select_prompt_provider = vi.fn(async (provider) => ({ ok: true, value: {
    ...promptSettings, provider, chatgpt_model: "available-gpt",
  } }));
  render(<App />);
  const selector = await screen.findByRole("combobox", { name: "프롬프트 작성 모델" });
  await user.selectOptions(selector, "chatgpt");
  await screen.findByRole("combobox", { name: "프롬프트 작성 모델" });
  expect(api.select_prompt_provider).toHaveBeenCalledWith("chatgpt");
  await user.selectOptions(selector, "local");
  await waitFor(() => expect(selector).toHaveProperty("value", "local"));
  expect(api.select_prompt_provider).toHaveBeenLastCalledWith("local");
});

it("keeps the previous prompt provider when saving a switch fails", async () => {
  const user = userEvent.setup();
  promptProviderBootstrap("local", true);
  api.select_prompt_provider = vi.fn(async () => ({
    ok: false, error: { code: "DATABASE_FAILED", message: "private" },
  }));
  render(<App />);
  const selector = await screen.findByRole("combobox", { name: "프롬프트 작성 모델" });
  await user.selectOptions(selector, "chatgpt");
  await screen.findByRole("alert");
  expect((selector as HTMLSelectElement).value).toBe("local");
  expect(screen.queryByText(/ChatGPT 구독 사용 중/)).toBeNull();
});

it("blocks natural-language generation until one prompt provider is ready", async () => {
  promptProviderBootstrap("local", false);
  api.bootstrap.mockImplementationOnce(async () => ({ ok: true, value: {
    language: "ko", project: current, projects: [empty], settings, image_models: imageModels,
    generation_defaults: {}, prompt_settings: promptSettings,
    models: imageModels[0].asset_ids.map((id) => ({ id, available: true })), chatgpt: null,
  } }));
  render(<App />);
  const dialog = await screen.findByRole("dialog", { name: "모델 준비" });
  fireEvent.click(within(dialog).getAllByRole("button", { name: "닫기" }).at(-1)!);
  fireEvent.change(screen.getByRole("textbox", { name: "이미지 요청" }), { target: { value: "girl" } });
  expect((screen.getByRole("button", { name: "전송" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.keyDown(screen.getByRole("textbox", { name: "이미지 요청" }), { key: "Enter" });
  expect(api.submit_request).not.toHaveBeenCalled();
});

it("shows the first ChatGPT plan confirmation and persists acknowledgement", async () => {
  promptProviderBootstrap("chatgpt", false);
  api.bootstrap.mockImplementationOnce(async () => ({ ok: true, value: {
    language: "ko", project: current, projects: [empty], settings, image_models: imageModels,
    generation_defaults: {}, prompt_settings: { ...promptSettings, provider: "chatgpt", chatgpt_model: "gpt" },
    models: imageModels[0].asset_ids.map((id) => ({ id, available: true })),
    chatgpt: { ...chatgptStatus, welcome_pending: true },
  } }));
  api.dismiss_chatgpt_welcome = vi.fn(async () => ({ ok: true, value: chatgptStatus }));
  render(<App />);
  await screen.findByRole("dialog", { name: "ChatGPT 구독을 사용합니다" });
  fireEvent.click(screen.getByRole("button", { name: "확인" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(api.dismiss_chatgpt_welcome).toHaveBeenCalledOnce();
});

it("prepares a GPT model without activating ChatGPT or requiring local files", async () => {
  const user = userEvent.setup();
  promptProviderBootstrap("local", false);
  const result = await api.bootstrap();
  api.bootstrap.mockResolvedValue({ ...result, value: { ...result.value,
    prompt_settings: { ...promptSettings, provider: "local", chatgpt_model: "" },
  } });
  api.get_chatgpt_models = vi.fn(async () => ({ ok: true, value: [
    { slug: "available-gpt", display_name: "Available GPT" },
  ] }));
  api.select_prompt_provider = vi.fn(async (provider) => ({ ok: true, value: {
    ...promptSettings, provider, chatgpt_model: "available-gpt",
  } }));
  render(<App />);
  const dialog = await screen.findByRole("dialog", { name: "모델 준비" });
  await user.selectOptions(within(dialog).getByRole("combobox", { name: "프롬프트 작성 모델" }), "chatgpt");
  await within(dialog).findByRole("option", { name: "Available GPT" });
  await user.selectOptions(within(dialog).getByLabelText("GPT 모델"), "available-gpt");
  expect(api.configure_prompt_writer).toHaveBeenCalledWith({ chatgpt_model: "available-gpt" });
  expect(api.update_settings).not.toHaveBeenCalled();
  expect(api.select_prompt_provider).not.toHaveBeenCalled();
  expect(within(dialog).queryByRole("button", { name: /프롬프트 작성|설정 저장/ })).toBeNull();
  await user.keyboard("{Escape}");
  const selector = screen.getByRole("combobox", { name: "프롬프트 작성 모델" });
  expect(selector).toHaveProperty("value", "local");
  await user.selectOptions(selector, "chatgpt");
  expect(api.select_prompt_provider).toHaveBeenCalledWith("chatgpt");
});

it("shows only the selected prompt writer's preparation and retains its saved GPT model", async () => {
  promptProviderBootstrap("local", true);
  api.select_prompt_provider = vi.fn();
  api.get_chatgpt_models = vi.fn(async () => ({ ok: true, value: [
    { slug: "available-gpt", display_name: "Available GPT" },
    { slug: "another-gpt", display_name: "Another GPT" },
  ] }));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByRole("button", { name: "모델 준비" }));
  const dialog = within(screen.getByRole("dialog", { name: "모델 준비" }));
  expect(dialog.getByRole("group", { name: "로컬 LLM" })).toBeTruthy();
  expect(dialog.getAllByText("로컬 LLM")).toHaveLength(1);
  expect(dialog.getByRole("separator")).toBeTruthy();
  expect(dialog.getByRole("region", { name: "이미지 생성 모델" })
    .compareDocumentPosition(dialog.getByRole("region", { name: "프롬프트 작성 모델" }))
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(dialog.queryByRole("button", { name: "ChatGPT 로그인" })).toBeNull();
  expect(dialog.queryByText("고급 설정")).toBeNull();
  expect(dialog.queryByLabelText("컨텍스트 크기")).toBeNull();
  expect(dialog.queryByLabelText("최근 요청 수")).toBeNull();
  expect(dialog.queryByRole("button", { name: "저장" })).toBeNull();
  await user.selectOptions(dialog.getByRole("combobox", { name: "프롬프트 작성 모델" }), "chatgpt");
  expect(dialog.queryByRole("group", { name: "로컬 LLM" })).toBeNull();
  expect(dialog.getAllByText("ChatGPT")).toHaveLength(1);
  expect(dialog.getByLabelText("계정")).toBeTruthy();
  expect(dialog.queryByLabelText("컨텍스트 크기")).toBeNull();
  expect(dialog.queryByLabelText("최근 요청 수")).toBeNull();
  expect(dialog.queryByRole("button", { name: "저장" })).toBeNull();
  expect(dialog.getByRole("button", { name: "계정 추가" })).toBeTruthy();
  await dialog.findByRole("option", { name: "Another GPT" });
  await user.selectOptions(dialog.getByLabelText("GPT 모델"), "another-gpt");
  await user.selectOptions(dialog.getByRole("combobox", { name: "프롬프트 작성 모델" }), "local");
  expect(dialog.getByRole("group", { name: "로컬 LLM" })).toBeTruthy();
  expect(dialog.queryByLabelText("GPT 모델")).toBeNull();
  await user.selectOptions(dialog.getByRole("combobox", { name: "프롬프트 작성 모델" }), "chatgpt");
  await dialog.findByRole("option", { name: "Another GPT" });
  expect(dialog.getByLabelText("GPT 모델")).toHaveProperty("value", "another-gpt");
  expect(api.configure_prompt_writer).toHaveBeenCalledExactlyOnceWith({ chatgpt_model: "another-gpt" });
  expect(api.update_settings).not.toHaveBeenCalled();
  expect(api.select_prompt_provider).not.toHaveBeenCalled();
});

it("saves provider and inference drafts together when generation settings close", async () => {
  promptProviderBootstrap("local", true);
  api.get_chatgpt_models = vi.fn();
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByLabelText("생성 설정"));
  const dialog = within(screen.getByRole("dialog", { name: "생성 설정" }));
  expect(dialog.queryByRole("button", { name: "ChatGPT 로그인" })).toBeNull();
  expect(dialog.queryByRole("button", { name: "로그아웃" })).toBeNull();
  expect(dialog.queryByLabelText("GPT 모델")).toBeNull();
  expect(dialog.queryByRole("button", { name: "파일 선택" })).toBeNull();
  expect(dialog.queryByRole("button", { name: "저장" })).toBeNull();
  await user.click(dialog.getByText("고급 설정"));
  const writerChoice = dialog.getByLabelText("프롬프트 작성 모델");
  const divider = dialog.getByRole("separator");
  expect(dialog.getByLabelText("너비").compareDocumentPosition(divider)
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(divider.compareDocumentPosition(writerChoice)
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(dialog.getByLabelText("너비").compareDocumentPosition(writerChoice)
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(writerChoice.compareDocumentPosition(dialog.getByLabelText("컨텍스트 크기"))
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(dialog.queryByRole("button", { name: "저장" })).toBeNull();
  await user.clear(dialog.getByLabelText("컨텍스트 크기"));
  await user.type(dialog.getByLabelText("컨텍스트 크기"), "8192");
  await user.clear(dialog.getByLabelText("생성 단계"));
  await user.type(dialog.getByLabelText("생성 단계"), "15");
  await user.selectOptions(dialog.getByLabelText("프롬프트 작성 모델"), "chatgpt");
  for (const label of ["컨텍스트 크기", "출력 토큰 한도", "추론 사용"]) {
    expect(dialog.queryByLabelText(label)).toBeNull();
  }
  await waitFor(() => expect(dialog.getByLabelText("추론 수준")).toHaveProperty("disabled", false));
  expect(dialog.getByLabelText("추론 수준")).toHaveProperty("value", "default");
  await user.selectOptions(dialog.getByLabelText("추론 수준"), "high");
  await user.clear(dialog.getByLabelText("최근 요청 수"));
  await user.type(dialog.getByLabelText("최근 요청 수"), "6");
  await user.selectOptions(dialog.getByLabelText("프롬프트 작성 모델"), "local");
  expect(dialog.getByLabelText("컨텍스트 크기")).toHaveProperty("value", "8192");
  expect(dialog.getByLabelText("최근 요청 수")).toHaveProperty("value", "6");
  expect(dialog.getByLabelText("추론 수준")).toHaveProperty("value", "medium");
  await user.selectOptions(dialog.getByLabelText("프롬프트 작성 모델"), "chatgpt");
  expect(dialog.getByLabelText("추론 수준")).toHaveProperty("value", "high");
  expect(api.update_settings).not.toHaveBeenCalled();
  expect(api.configure_prompt_writer).not.toHaveBeenCalled();
  await user.click(dialog.getByText("닫기", { selector: "button" }));
  expect(api.update_settings).toHaveBeenCalledExactlyOnceWith({ ...settings, steps: 15 }, {
    ...promptSettings, provider: "chatgpt", chatgpt_model: "available-gpt",
    context_size: 8192, history_turns: 6,
    chatgpt_reasoning_effort: "high",
  });
  expect(screen.queryByRole("dialog", { name: "생성 설정" })).toBeNull();
  expect(api.get_chatgpt_models).not.toHaveBeenCalled();
});

it.each(["button", "header", "escape", "overlay"])("saves generation settings before closing through %s", async (method) => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByLabelText("생성 설정"));
  const dialog = screen.getByRole("dialog", { name: "생성 설정" });
  await user.clear(within(dialog).getByLabelText("생성 단계"));
  await user.type(within(dialog).getByLabelText("생성 단계"), "12");
  expect(api.update_settings).not.toHaveBeenCalled();
  if (method === "button") await user.click(within(dialog).getByText("닫기", { selector: "button" }));
  if (method === "header") await user.click(within(dialog).getByLabelText("닫기"));
  if (method === "escape") await user.keyboard("{Escape}");
  if (method === "overlay") await user.click(dialog.parentElement!);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(api.update_settings).toHaveBeenCalledExactlyOnceWith({ ...settings, steps: 12 }, promptSettings);
  await user.click(screen.getByLabelText("생성 설정"));
  expect(screen.getByLabelText("생성 단계")).toHaveProperty("value", "12");
});

it("retains the generation settings draft when saving on close fails and allows retry", async () => {
  api.update_settings.mockResolvedValueOnce({ ok: false, error: { code: "DATABASE_FAILED" } });
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByLabelText("생성 설정"));
  await user.clear(screen.getByLabelText("생성 단계"));
  await user.type(screen.getByLabelText("생성 단계"), "12");
  await user.keyboard("{Escape}");
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "작업 기록을 저장하거나 불러올 수 없습니다.");
  expect(screen.getByRole("dialog", { name: "생성 설정" })).toBeTruthy();
  expect(screen.getByLabelText("생성 단계")).toHaveProperty("value", "12");
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(api.update_settings).toHaveBeenCalledTimes(2);
});

it("keeps settings locked and ignores repeated close requests until saving completes", async () => {
  let finish!: (value: unknown) => void;
  api.update_settings.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByLabelText("생성 설정"));
  const dialog = screen.getByRole("dialog", { name: "생성 설정" });
  await user.clear(screen.getByLabelText("생성 단계"));
  await user.type(screen.getByLabelText("생성 단계"), "12");
  await user.click(within(dialog).getByText("닫기", { selector: "button" }));
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).matches(":disabled")).toBe(true);
  await user.keyboard("{Escape}");
  await user.click(within(dialog).getByLabelText("닫기"));
  await user.click(dialog.parentElement!);
  expect(api.update_settings).toHaveBeenCalledOnce();
  expect(screen.getByRole("dialog", { name: "생성 설정" })).toBe(dialog);
  await act(async () => finish({ ok: true, value: { ...settings, steps: 12 } }));
  expect(screen.queryByRole("dialog")).toBeNull();
});

it.each(["너비", "컨텍스트 크기"])("keeps invalid %s available for correction instead of saving on close", async (label) => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByLabelText("생성 설정"));
  if (label === "컨텍스트 크기") await user.click(screen.getByText("고급 설정"));
  const input = screen.getByLabelText(label) as HTMLInputElement;
  await user.clear(input);
  if (label === "컨텍스트 크기") await user.click(screen.getByText("고급 설정"));
  await user.keyboard("{Escape}");
  expect(api.update_settings).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog", { name: "생성 설정" })).toBeTruthy();
  expect(input.value).toBe("");
  expect(input.validity.valid).toBe(false);
  if (label === "컨텍스트 크기") expect(input.closest("details")?.open).toBe(true);
  await user.type(input, label === "너비" ? "832" : "8192");
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(api.update_settings).toHaveBeenCalledOnce();
});

it("returns to the selected ChatGPT setup after the first sign-in welcome", async () => {
  promptProviderBootstrap("local", false);
  const result = await api.bootstrap();
  api.bootstrap.mockResolvedValue({ ...result, value: { ...result.value, chatgpt: {
    ...chatgptStatus, connected: false, plan_enabled: false, active_account: null,
    accounts: [], email: null,
  } } });
  api.login_chatgpt = vi.fn(async () => ({ ok: true, value: { ...chatgptStatus, welcome_pending: true } }));
  api.dismiss_chatgpt_welcome = vi.fn(async () => ({ ok: true, value: chatgptStatus }));
  api.get_chatgpt_models = vi.fn(async () => ({ ok: true, value: [
    { slug: "available-gpt", display_name: "Available GPT" },
  ] }));
  const user = userEvent.setup();
  render(<App />);
  const dialog = await screen.findByRole("dialog", { name: "모델 준비" });
  await user.selectOptions(within(dialog).getByRole("combobox", { name: "프롬프트 작성 모델" }), "chatgpt");
  await user.click(within(dialog).getByRole("button", { name: "ChatGPT 로그인" }));
  const welcome = await screen.findByRole("dialog", { name: "ChatGPT 구독을 사용합니다" });
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  await user.click(within(welcome).getByRole("button", { name: "확인" }));
  const resumed = within(await screen.findByRole("dialog", { name: "모델 준비" }));
  expect(resumed.getByRole("combobox", { name: "프롬프트 작성 모델" })).toHaveProperty("value", "chatgpt");
  expect(resumed.queryByLabelText("컨텍스트 크기")).toBeNull();
  expect(await resumed.findByRole("option", { name: "Available GPT" })).toBeTruthy();
});

it.each([
  ["no GPT model", "", chatgptStatus],
  ["disconnected account", "available-gpt", { ...chatgptStatus, connected: false }],
  ["missing permission", "available-gpt", { ...chatgptStatus, plan_enabled: false }],
  ["pending sign-in", "available-gpt", { ...chatgptStatus, login_state: "waiting" }],
])("disables ChatGPT in both selectors with %s", async (_reason, model, status) => {
  promptProviderBootstrap("local", true);
  const result = await api.bootstrap();
  api.bootstrap.mockResolvedValue({ ...result, value: { ...result.value,
    prompt_settings: { ...promptSettings, provider: "local", chatgpt_model: model },
    chatgpt: status,
  } });
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  const composerSelect = screen.getByLabelText("프롬프트 작성 모델");
  expect(within(composerSelect).getByRole("option", { name: "ChatGPT" })).toHaveProperty("disabled", true);
  await user.click(screen.getByLabelText("생성 설정"));
  const select = within(screen.getByRole("dialog", { name: "생성 설정" }))
    .getByLabelText("프롬프트 작성 모델") as HTMLSelectElement;
  expect(within(select).getByRole("option", { name: "ChatGPT" })).toHaveProperty("disabled", true);
  await user.selectOptions(select, "chatgpt");
  expect(select.value).toBe("local");
});

it("keeps a local prompt download cancellable while viewing ChatGPT setup", async () => {
  promptProviderBootstrap("chatgpt", false);
  const result = await api.bootstrap();
  const models = [{ id: "prompt", available: false, download: {
    model_id: "prompt", state: "downloading", received: 50, total: 100, error_code: null,
  } }, ...imageModels[0].asset_ids.map((id) => ({ id, available: true }))];
  api.bootstrap.mockResolvedValue({ ...result, value: { ...result.value, models } });
  api.get_model_status.mockResolvedValue({ ok: true, value: models });
  api.get_chatgpt_models = vi.fn(async () => ({ ok: true, value: [
    { slug: "available-gpt", display_name: "Available GPT" },
  ] }));
  api.cancel_model_download = vi.fn(async () => ({ ok: true, value: models }));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByRole("button", { name: "모델 준비" }));
  const downloads = within(screen.getByRole("region", { name: "다른 모델의 다운로드" }));
  expect(downloads.getByText("50%")).toBeTruthy();
  await user.click(downloads.getByRole("button", { name: "취소" }));
  expect(api.cancel_model_download).toHaveBeenCalledWith("prompt");
  expect(screen.queryByLabelText("컨텍스트 크기")).toBeNull();
});

describe("display language", () => {
  it("switches beside the logo without changing a draft or project, and restores the saved language", async () => {
    let language = "ko";
    api.bootstrap.mockImplementation(() => Promise.resolve({ ok: true, value: {
      language, project: current, projects: [empty], settings,
      image_models: imageModels,
        generation_defaults: {}, prompt_settings: promptSettings,
    }}));
    api.set_language = vi.fn(async (next) => {
      language = next as string;
      return { ok: true, value: language };
    });
    const user = userEvent.setup();
    const app = render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.type(screen.getByRole("textbox", { name: "이미지 요청" }), "고양이 by the sea");
    const languageSelector = screen.getByRole("combobox", { name: "언어" });
    expect(languageSelector.closest("header")?.textContent).toContain("moru");
    await user.selectOptions(languageSelector, "en");
    expect(await screen.findByText("What scene shall we draw?")).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Image request" }) as HTMLTextAreaElement).value).toBe("고양이 by the sea");
    expect(document.documentElement.lang).toBe("en");
    expect(api.submit_request).not.toHaveBeenCalled();
    expect(api.create_project).not.toHaveBeenCalled();
    app.unmount();
    render(<App />);
    expect(await screen.findByText("What scene shall we draw?")).toBeTruthy();
    expect((screen.getByRole("combobox", { name: "Language" }) as HTMLSelectElement).value).toBe("en");
    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "ko");
    expect(await screen.findByText("어떤 장면을 그릴까요?")).toBeTruthy();
    expect(document.documentElement.lang).toBe("ko");
  });

  it("keeps the current language and reports an error when saving the selection fails", async () => {
    api.set_language = vi.fn(async () => ({ ok: false, error: { code: "DATABASE_FAILED", message: "internal details" } }));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.selectOptions(screen.getByRole("combobox", { name: "언어" }), "en");
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "작업 기록을 저장하거나 불러올 수 없습니다.");
    expect((screen.getByRole("combobox", { name: "언어" }) as HTMLSelectElement).value).toBe("ko");
  });

  it("localizes settings and persisted failures without translating user content", async () => {
    current = { ...withImage, unfinished_requests: [{
      id: "failed", text: "한국어 user request", status: "failed", turn_id: null,
      width: 1024, height: 1024,
      error_code: "CUDA_OOM", message: "old Korean diagnostic",
    }] };
    api.set_language = vi.fn(async (language) => ({ ok: true, value: language }));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.selectOptions(screen.getByRole("combobox", { name: "언어" }), "en");
    expect(await screen.findByText("There is not enough GPU memory. Please reduce the image size.")).toBeTruthy();
    expect(screen.getByText("한국어 user request")).toBeTruthy();
    expect(screen.getByText("소녀를 그려줘")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Generation settings" }));
    expect(screen.getByRole("dialog", { name: "Generation settings" })).toBeTruthy();
    expect(screen.getByLabelText("Width")).toBeTruthy();
    expect(screen.getByLabelText("Context size")).toBeTruthy();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Model setup" }));
    expect(screen.queryByLabelText("Context size")).toBeNull();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(await screen.findByRole("dialog", { name: "Prompt" })).toBeTruthy();
    expect((within(screen.getByRole("dialog", { name: "Prompt" })).getByRole("textbox") as HTMLTextAreaElement).value).toBe("private actual prompt");
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "View image full screen" }));
    expect(screen.getByRole("dialog", { name: "Image viewer" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Fit to screen" })).toBeTruthy();
  });
});

it("retranslates an existing error banner when changing the display language", async () => {
  api.set_language = vi.fn(async (language) => ({ ok: true, value: language }));
  api.create_project.mockResolvedValue({ ok: false, error: { code: "DATABASE_FAILED", message: "old message" } });
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  await user.click(screen.getByRole("button", { name: "새 작업" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "작업 기록을 저장하거나 불러올 수 없습니다.");
  await user.selectOptions(screen.getByRole("combobox", { name: "언어" }), "en");
  await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Could not save or load the project history."));
});

it("does not allow a language change before the saved language has loaded", async () => {
  let finish!: (value: unknown) => void;
  api.bootstrap.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<App />);
  expect((screen.getByRole("combobox", { name: "언어" }) as HTMLSelectElement).disabled).toBe(true);
  await waitFor(() => expect(api.bootstrap).toHaveBeenCalled());
  await act(async () => finish({ ok: true, value: {
    language: "en", project: empty, projects: [empty], settings,
    image_models: imageModels,
        generation_defaults: {}, prompt_settings: promptSettings,
  } }));
  expect((screen.getByRole("combobox", { name: "Language" }) as HTMLSelectElement).disabled).toBe(false);
});

it.each([
  ["en", "Could not load the model."],
  ["ko", "모델을 불러올 수 없습니다."],
])("uses saved %s for an error even when bootstrap fails", async (language, message) => {
  api.get_language.mockResolvedValue({ ok: true, value: language });
  api.bootstrap.mockResolvedValue({ ok: false, error: { code: "MODEL_LOAD_FAILED", message: "stale Korean error" } });
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", message);
  expect(document.documentElement.lang).toBe(language);
});

it.each(["unreadable", "unsupported"])("uses English when the saved preference is %s and bootstrap fails", async (failure) => {
  api.get_language.mockResolvedValue(failure === "unreadable"
    ? { ok: false, error: { code: "DATABASE_FAILED", message: "private details" } }
    : { ok: true, value: "fr" });
  api.bootstrap.mockResolvedValue({ ok: false, error: { code: "DATABASE_FAILED", message: "Korean message" } });
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Could not save or load the project history.");
  expect(document.documentElement.lang).toBe("en");
});


it("restores FLUX with its own files and saves family changes only in generation settings", async () => {
  const bootstrap = await api.bootstrap();
  const saved = { ...settings, model_id: "flux2-klein-4b", steps: 4, cfg: 1,
    width: 832, height: 1216, seed: "42" };
  api.bootstrap.mockResolvedValue({ ...bootstrap, value: { ...bootstrap.value,
    settings: saved,
    models: ["prompt", "flux2-klein-4b", "flux2_text_encoder", "flux2_vae"]
      .map((id) => ({ id, available: true })),
  } });
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText("어떤 장면을 그릴까요?");
  expect(screen.queryByRole("dialog")).toBeNull();
  await user.click(screen.getByRole("button", { name: "모델 준비" }));
  expect((screen.getByLabelText("모델") as HTMLSelectElement).value).toBe("flux2");
  await user.selectOptions(screen.getByLabelText("모델"), "anima");
  await user.keyboard("{Escape}");
  expect(api.update_settings).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText("생성 설정"));
  expect((screen.getByLabelText("모델") as HTMLSelectElement).value).toBe("flux2");
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("4");
  await user.selectOptions(screen.getByLabelText("모델"), "anima");
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("10");
  await user.selectOptions(screen.getByLabelText("모델"), "flux2");
  expect((screen.getByLabelText("생성 단계") as HTMLInputElement).value).toBe("4");
  expect((screen.getByLabelText("프롬프트 반영 강도 (CFG)") as HTMLInputElement).value).toBe("1");
  expect((screen.getByLabelText("시드") as HTMLInputElement).value).toBe("42");
  await user.click(screen.getByText("닫기", { selector: "button" }));
  expect(api.update_settings).not.toHaveBeenCalled();
});
