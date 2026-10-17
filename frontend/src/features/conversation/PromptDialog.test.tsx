import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { BridgeError } from "../../api";
import PromptDialog from "./PromptDialog";
import { imagePoint } from "./imageViewport";
import type { EditDraft } from "./editDraft";

const details = { id: "one", prompt: "A woman holds a white cup.", model_name: "Anima Turbo",
  settings: { model_id: "anima-turbo-v1.1", width: 64, height: 64, steps: 10, cfg: 1, seed: "42" } };
const draft: EditDraft = { prompt: details.prompt, content: "이 컵을 파란색으로 바꿔",
  strokes: [{ points: [{ x: .5, y: .5 }], sizePx: 32, erase: false }] };

beforeEach(() => {
  window.pywebview = { api: { set_edit_tab: vi.fn(async () => ({ ok: true as const, value: null })) } };
  const context = { clearRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
    stroke: vi.fn(), putImageData: vi.fn(), getImageData: vi.fn(() => ({ data: new Uint8ClampedArray([255, 255, 255, 255]) })) };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as never);
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,MASK");
});

it("opens the previously saved region tab and restores this image's draft", () => {
  render(<PromptDialog details={{ ...details, edit_tab: "region" }} draft={draft}
    source="data:image/png;base64,IMAGE" regionReady onClose={vi.fn()} onGenerate={vi.fn()} />);
  expect(screen.getByRole("tab", { name: "영역" }).getAttribute("aria-selected")).toBe("true");
  expect((screen.getByLabelText("수정 요청") as HTMLTextAreaElement).value).toBe("이 컵을 파란색으로 바꿔");
  expect(screen.getByPlaceholderText("무엇을 어떻게 바꿀지 설명하세요")).toBeTruthy();
});

it("preserves both editors while switching tabs and saves the preference", async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  render(<PromptDialog details={details} draft={draft} onDraft={changed}
    source="data:image/png;base64,IMAGE" regionReady onClose={vi.fn()} onGenerate={vi.fn()} />);
  const prompt = screen.getByLabelText("실제 생성 프롬프트");
  await user.clear(prompt);
  await user.type(prompt, "A woman in a blue room.");
  await user.click(screen.getByRole("tab", { name: "영역" }));
  expect((await screen.findByLabelText("수정 요청") as HTMLTextAreaElement).value).toBe("이 컵을 파란색으로 바꿔");
  expect(window.pywebview!.api.set_edit_tab).toHaveBeenCalledWith("region");
  await user.click(screen.getByRole("tab", { name: "프롬프트" }));
  expect((await screen.findByLabelText("실제 생성 프롬프트") as HTMLTextAreaElement).value)
    .toBe("A woman in a blue room.");
  expect(changed.mock.lastCall![0].strokes).toEqual(draft.strokes);
});

it("submits the modification request and mask once without adding an editor conversation", async () => {
  let admit!: () => void;
  const generate = vi.fn(() => new Promise<void>((resolve) => { admit = resolve; }));
  const close = vi.fn();
  render(<PromptDialog details={{ ...details, edit_tab: "region" }} draft={draft}
    source="data:image/png;base64,IMAGE" regionReady onClose={close} onGenerate={vi.fn()}
    onRegionGenerate={generate} />);
  const button = screen.getByRole("button", { name: "생성" });
  fireEvent.click(button); fireEvent.click(button);
  expect(generate).toHaveBeenCalledExactlyOnceWith("이 컵을 파란색으로 바꿔", "data:image/png;base64,MASK");
  expect(close).not.toHaveBeenCalled();
  admit();
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
});

it("keeps the mask and modification request available after admission fails", async () => {
  const close = vi.fn();
  render(<PromptDialog details={{ ...details, edit_tab: "region" }} draft={draft}
    source="data:image/png;base64,IMAGE" regionReady onClose={close} onGenerate={vi.fn()}
    onRegionGenerate={vi.fn(async () => { throw new BridgeError("REGION_INVALID_RESPONSE"); })} />);
  await userEvent.click(screen.getByRole("button", { name: "생성" }));
  expect((await screen.findByRole("alert")).textContent).toContain("프롬프트");
  expect((screen.getByLabelText("수정 요청") as HTMLTextAreaElement).value).toBe("이 컵을 파란색으로 바꿔");
  expect((screen.getByRole("button", { name: "되돌리기" }) as HTMLButtonElement).disabled).toBe(false);
  expect(close).not.toHaveBeenCalled();
});

it("does not generate with no selection or with missing prompt preparation", () => {
  render(<PromptDialog details={{ ...details, edit_tab: "region" }}
    draft={{ ...draft, strokes: [] }} source="image" regionReady={false}
    onClose={vi.fn()} onGenerate={vi.fn()} onRegionGenerate={vi.fn()} />);
  expect((screen.getByRole("button", { name: "생성" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("프롬프트 제공자를 준비하고 Anima 모델을 선택해 주세요.")).toBeTruthy();
});

it("maps painting coordinates from the displayed image back to normalized original coordinates", () => {
  expect(imagePoint(250, 200, { left: 100, top: 50, width: 300, height: 600 }))
    .toEqual({ x: .5, y: .25 });
  expect(imagePoint(-20, 900, { left: 0, top: 0, width: 300, height: 600 }))
    .toEqual({ x: 0, y: 1 });
});

it.each(["prompt", "region"] as const)("describes source generation settings on the generate tooltip in the %s tab", (tab) => {
  render(<PromptDialog details={{ ...details, edit_tab: tab, settings: { ...details.settings, seed: null } }}
    source="image" regionReady onClose={vi.fn()} onGenerate={vi.fn()} />);
  const generate = screen.getByRole("button", { name: "생성" });
  const tooltip = document.getElementById(generate.getAttribute("aria-describedby")!)!;
  expect(tooltip.getAttribute("role")).toBe("tooltip");
  expect(tooltip.textContent).toContain("원본 생성 정보");
  expect(tooltip.textContent).toContain("모델: Anima Turbo");
  expect(tooltip.textContent).toContain("너비 / 높이: 64 × 64");
  expect(tooltip.textContent).toContain("시드: 자동");
  expect(screen.queryByText("생성 정보")).toBeNull();
  expect(screen.getAllByRole("button", { name: "닫기" })).toHaveLength(1);
});

it("keeps the region editor focused on selection and content instead of repeated instructions", () => {
  render(<PromptDialog details={{ ...details, edit_tab: "region" }} source="image" regionReady
    onClose={vi.fn()} onGenerate={vi.fn()} onRegionGenerate={vi.fn()} />);
  expect(screen.queryByText("생성 정보")).toBeNull();
  expect(screen.queryByText("선택한 곳에 들어갈 내용을 적어 주세요.")).toBeNull();
  expect(screen.queryByText("생성할 영역을 칠해 주세요.")).toBeNull();
  expect(screen.getByRole("button", { name: "붓" }).getAttribute("title")).toBe("붓");
  expect(screen.getByRole("slider", { name: /붓 크기/ })).toBeTruthy();
  expect(screen.getByLabelText("수정 요청")).toBeTruthy();
});
