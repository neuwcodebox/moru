import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Mock } from "vitest";
import App from "./App";
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
  context_size: 8192,
  max_tokens: 4096,
  thinking: true,
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
  request_text: "소녀를 그려줘",
  created_at: empty.created_at,
  parent_image_id: null,
  siblings: ["i1"],
};
const withImage: Project = { ...empty, active_leaf_id: "i1", images: [image] };
let current: Project;
let api: Record<string, Mock<(...args: any[]) => Promise<any>>>;
beforeEach(() => {
  current = structuredClone(empty);
  const success = (value: unknown) => Promise.resolve({ ok: true, value });
  api = {
    bootstrap: vi.fn(() =>
      success({
        project: current,
        projects: [empty],
        settings,
        prompt_settings: promptSettings,
      }),
    ),
    get_project: vi.fn(() => success(current)),
    list_projects: vi.fn(() => success([empty])),
    get_image_source: vi.fn(() => success("data:image/png;base64,abc")),
    submit_request: vi.fn(() => {
      current = withImage;
      return success({
        id: "j1",
        project_id: "p1",
        state: "queued",
        request_id: "r1",
      });
    }),
    get_job: vi.fn(() =>
      success({ id: "j1", project_id: "p1", state: "completed" }),
    ),
    cancel_job: vi.fn(() => success(undefined)),
    copy_prompt: vi.fn(() => success(undefined)),
    fork: vi.fn((_id, base) => {
      current = { ...current, fork_image_id: base as string | null };
      return success(current);
    }),
    get_image_details: vi.fn(() =>
      success({
        id: "i1",
        prompt: "private actual prompt",
        settings: { ...settings, seed: "42" },
      }),
    ),
    generate_from_prompt: vi.fn(() =>
      success({ id: "j1", project_id: "p1", state: "queued" }),
    ),
    update_settings: vi.fn((values) => success(values)),
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
      return success({ id: "j1", project_id: "p1", state: "queued" });
    }),
    create_project: vi.fn(() => {
      current = { ...empty, id: "p2" };
      return success(current);
    }),
    select_branch: vi.fn(() => success(current)),
  };
  window.pywebview = { api };
});

describe("conversation", () => {
  it("closes the manual prompt dialog when generation is accepted even if refreshing the conversation fails", async () => {
    current = withImage;
    api.get_project.mockRejectedValue(new Error("대화를 불러올 수 없습니다."));
    api.get_job.mockResolvedValue({
      ok: true,
      value: { id: "j1", project_id: "p1", state: "prompting" },
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("프롬프트"));
    await user.click(screen.getByText("이 프롬프트로 생성"));
    await screen.findByText("생각 중…");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.generate_from_prompt).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert").textContent).toContain(
      "대화를 불러올 수 없습니다.",
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
        },
      ],
    };
    api.get_job.mockResolvedValue({
      ok: true,
      value: { id: "j1", project_id: "p1", state: "prompting" },
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("이미지 생성에 실패했습니다.");
    await user.click(screen.getByText("재시도"));
    await screen.findByText("생각 중…");
    expect(screen.queryByText("이미지 생성에 실패했습니다.")).toBeNull();
    expect(api.retry_request).toHaveBeenCalledWith("r1");
  });
  it("copies the edited prompt through the desktop clipboard bridge", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("프롬프트"));
    const editor = screen.getByLabelText("실제 생성 프롬프트");
    await user.clear(editor);
    await user.type(editor, "edited image prompt");
    await user.click(screen.getByText("복사"));
    expect(api.copy_prompt).toHaveBeenCalledWith("edited image prompt");
    expect(await screen.findByText("복사했습니다.")).toBeTruthy();
  });

  it("shows a compact thinking status inside the conversation while writing the prompt", async () => {
    const user = userEvent.setup();
    api.get_job.mockResolvedValue({
      ok: true,
      value: { id: "j1", project_id: "p1", state: "prompting" },
    });
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.type(
      screen.getByLabelText("이미지 요청"),
      "소녀를 그려줘{Enter}",
    );
    const conversation = screen.getByRole("main", { name: "대화" });
    const thinking = await within(conversation).findByText("생각 중…");
    const status = thinking.closest('[role="status"]') as HTMLElement;
    expect(screen.queryByText("프롬프트 준비")).toBeNull();
    expect(within(status).getByText("취소")).toBeTruthy();
    await user.click(within(status).getByText("취소"));
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

  it("selects a Fork base and lets the user cancel it", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("⑂ Fork"));
    expect(await screen.findByText("Fork: #i1")).toBeTruthy();
    await user.click(screen.getByLabelText("Fork 취소"));
    expect(api.fork).toHaveBeenLastCalledWith("p1", null);
    expect(screen.queryByText("Fork: #i1")).toBeNull();
  });

  it("exposes the prompt only in its dialog and submits manual edits as a Fork", async () => {
    current = withImage;
    const user = userEvent.setup();
    render(<App />);
    await screen.findByAltText("생성 이미지");
    await user.click(screen.getByText("프롬프트"));
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
    await user.click(screen.getByText("+ 새 작업"));
    await screen.findByText("어떤 장면을 그릴까요?");
    expect(screen.queryByText("Fork: #i1")).toBeNull();
    expect(api.create_project).toHaveBeenCalledOnce();
  });

  it("switches sibling branches from the branching image", async () => {
    current = {
      ...withImage,
      images: [
        image,
        { ...image, id: "i2", parent_image_id: "i1", siblings: ["i2", "i3"] },
      ],
    };
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("1 / 2");
    await user.click(screen.getByLabelText("다음 분기"));
    expect(api.select_branch).toHaveBeenCalledWith("p1", "i3");
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
    await user.type(screen.getByLabelText("Seed"), "9223372036854775807");
    await user.click(screen.getByText("저장"));
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
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 · 프롬프트 LLM"));
    const context = screen.getByLabelText("컨텍스트 크기");
    const output = screen.getByLabelText("출력 토큰 한도");
    const thinking = screen.getByLabelText("Thinking 사용") as HTMLInputElement;
    expect((context as HTMLInputElement).value).toBe("8192");
    expect((output as HTMLInputElement).value).toBe("4096");
    expect(thinking.checked).toBe(true);
    await user.clear(context);
    await user.type(context, "4096");
    await user.clear(output);
    await user.type(output, "2048");
    await user.click(thinking);
    await user.click(screen.getByText("저장"));
    expect(api.update_settings).toHaveBeenCalledWith(settings, {
      context_size: 4096,
      max_tokens: 2048,
      thinking: false,
    });
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 · 프롬프트 LLM"));
    expect(
      (screen.getByLabelText("컨텍스트 크기") as HTMLInputElement).value,
    ).toBe("4096");
    expect(
      (screen.getByLabelText("Thinking 사용") as HTMLInputElement).checked,
    ).toBe(false);
  });

  it("keeps the dialog open without saving when output leaves no input context", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("어떤 장면을 그릴까요?");
    await user.click(screen.getByLabelText("생성 설정"));
    await user.click(screen.getByText("고급 · 프롬프트 LLM"));
    const output = screen.getByLabelText("출력 토큰 한도");
    await user.clear(output);
    await user.type(output, "8192");
    await user.click(screen.getByText("저장"));
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
  expect(screen.getByText("100%")).toBeTruthy();
  await user.click(screen.getByLabelText("확대"));
  expect(screen.getByText("125%")).toBeTruthy();
  await user.click(screen.getByText("화면 맞춤"));
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
  await user.click(screen.getByText("화면 맞춤"));
  expect(image.style.transform).toBe("translate(0px, 0px) scale(1)");
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
