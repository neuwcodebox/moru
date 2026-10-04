import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import GenerationProgress from "./GenerationProgress";
import type { Job } from "./api";

const job: Job = {
  id: "j1",
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

it("updates live thinking and prompt inside the same placeholder as generation advances", () => {
  const { rerender } = render(<GenerationProgress job={job} />);
  const placeholder = screen.getByRole("region", { name: "생성 진행" });
  expect(within(placeholder).getByText("Choosing a scene")).toBeTruthy();
  rerender(
    <GenerationProgress
      job={{
        ...job,
        thinking_text: "Choosing a scene with rain",
        prompt_text: "girl, night",
      }}
    />,
  );
  expect(screen.getByRole("region", { name: "생성 진행" })).toBe(placeholder);
  expect(
    within(placeholder).getByText("Choosing a scene with rain"),
  ).toBeTruthy();
  expect(within(placeholder).getByText("girl, night")).toBeTruthy();
  rerender(
    <GenerationProgress
      job={{
        ...job,
        state: "generating",
        thinking_text: "Choosing a scene with rain",
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
        thinking_text: "",
        prompt_text: "night, girl",
      }}
    />,
  );
  expect(screen.getByText("프롬프트 작성 중…")).toBeTruthy();
  expect(screen.queryByText("생각 과정")).toBeNull();
  expect(screen.getByText("night, girl")).toBeTruthy();
});
