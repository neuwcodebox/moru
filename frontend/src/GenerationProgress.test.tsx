import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import GenerationProgress from "./GenerationProgress";
import type { Job } from "./api";

const job: Job & { thinking_text: string } = {
  id: "j1",
  width: 832,
  height: 1216,
  project_id: "p1",
  request_id: "r1",
  state: "prompting",
  step: null,
  total: null,
  image_id: null,
  error_code: null,
  thinking_enabled: true,
  thinking_text: "Choosing a scene",
  prompt_text: "",
};

it("shows only thinking status and streams the final prompt in the same placeholder", () => {
  const { rerender } = render(<GenerationProgress job={job} />);
  const placeholder = screen.getByRole("region", { name: "생성 진행" });
  expect(placeholder.style.aspectRatio).toBe("832 / 1216");
  expect(within(placeholder).getByText("생각 중…")).toBeTruthy();
  expect(within(placeholder).queryByText("Choosing a scene")).toBeNull();
  expect(within(placeholder).queryByText("생각 과정")).toBeNull();
  rerender(
    <GenerationProgress
      job={{
        ...job,
        prompt_text: "girl, night",
      }}
    />,
  );
  expect(screen.getByRole("region", { name: "생성 진행" })).toBe(placeholder);
  expect(
    within(placeholder).queryByText("Choosing a scene"),
  ).toBeNull();
  expect(within(placeholder).getByText("프롬프트 생성 중…")).toBeTruthy();
  expect(within(placeholder).getByText("girl, night")).toBeTruthy();
  rerender(
    <GenerationProgress
      job={{
        ...job,
        state: "generating",
        prompt_text: "girl, night, rain",
        step: 4,
        total: 10,
      }}
    />,
  );
  expect(screen.getByText("4 / 10")).toBeTruthy();
  expect(
    (
      screen.getByRole("progressbar", {
        name: "이미지 생성 단계",
      }) as HTMLProgressElement
    ).value,
  ).toBe(4);
  expect(within(placeholder).getByText("girl, night, rain")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "취소" })).toBeNull();
});

it("writes the prompt directly when thinking is disabled", () => {
  render(
    <GenerationProgress
      job={{
        ...job,
        thinking_enabled: false,
        prompt_text: "night, girl",
      }}
    />,
  );
  expect(screen.getByText("프롬프트 생성 중…")).toBeTruthy();
  expect(screen.queryByText("생각 과정")).toBeNull();
  expect(screen.getByText("night, girl")).toBeTruthy();
});

it("distinguishes prompt loading, inference and image loading in the same placeholder", () => {
  const { rerender } = render(<GenerationProgress job={{ ...job, state: "loading_prompt_model" }} />);
  const placeholder = screen.getByRole("region", { name: "생성 진행" });
  expect(within(placeholder).getByText("프롬프트 모델을 불러오는 중…")).toBeTruthy();
  expect(within(placeholder).queryByText("생각 중…")).toBeNull();
  rerender(<GenerationProgress job={job} />);
  expect(screen.getByRole("region", { name: "생성 진행" })).toBe(placeholder);
  expect(within(placeholder).getByText("생각 중…")).toBeTruthy();
  rerender(<GenerationProgress job={{ ...job, thinking_enabled: false }} />);
  expect(within(placeholder).getByText("프롬프트 생성 중…")).toBeTruthy();
  rerender(<GenerationProgress job={{ ...job, state: "loading_model" }} />);
  expect(within(placeholder).getByText("이미지 모델을 불러오는 중…")).toBeTruthy();
  expect(within(placeholder).queryByText("생각 중…")).toBeNull();
});


it("changes from thinking to tag lookup and final prompt in the same placeholder", () => {
  const cloud = { ...job, thinking_enabled: false };
  const { rerender } = render(<GenerationProgress job={{ ...cloud, state: "thinking" }} />);
  const placeholder = screen.getByRole("region", { name: "생성 진행" });
  const status = within(placeholder).getByRole("status");
  expect(within(status).getByText("생각 중…")).toBeTruthy();
  rerender(<GenerationProgress job={{ ...cloud, state: "searching_tags" }} />);
  expect(screen.getByRole("region", { name: "생성 진행" })).toBe(placeholder);
  expect(within(placeholder).getByRole("status")).toBe(status);
  expect(within(status).getByText("태그 검색 중…")).toBeTruthy();
  expect(within(placeholder).getByText("장면을 준비하고 있어요")).toBeTruthy();
  expect(screen.queryByText("곧 이미지가 여기에 나타나요")).toBeNull();
  rerender(<GenerationProgress job={{ ...cloud, state: "prompting" }} />);
  expect(within(status).getByText("프롬프트 생성 중…")).toBeTruthy();
  rerender(<GenerationProgress job={{ ...cloud, state: "prompting", prompt_text: "1girl" }} />);
  expect(within(placeholder).getByText("1girl")).toBeTruthy();
  expect(screen.getByRole("region", { name: "생성 진행" })).toBe(placeholder);
});


it("updates the found tag count inside the existing search status and hides it afterward", () => {
  const cloud = { ...job, thinking_enabled: false, state: "searching_tags", found_tag_count: 0 };
  const { rerender } = render(<GenerationProgress job={cloud} />);
  const placeholder = screen.getByRole("region", { name: "생성 진행" });
  const status = within(placeholder).getByRole("status");
  expect(within(status).getByText("태그 검색 중… (0개 찾음)")).toBeTruthy();
  rerender(<GenerationProgress job={{ ...cloud, found_tag_count: 12 }} />);
  expect(within(placeholder).getByRole("status")).toBe(status);
  expect(within(status).getByText("태그 검색 중… (12개 찾음)")).toBeTruthy();
  expect(screen.queryByRole("progressbar")).toBeNull();
  rerender(<GenerationProgress job={{ ...cloud, state: "prompting", found_tag_count: 12 }} />);
  expect(within(status).getByText("프롬프트 생성 중…")).toBeTruthy();
  expect(screen.queryByText(/개 찾음/)).toBeNull();
});
