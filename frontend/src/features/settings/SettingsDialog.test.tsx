import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ChatGPTStatus, PromptSettings } from "../../api";
import { generationSettings, imageModels } from "../../modelFixtures";
import SettingsDialog from "./SettingsDialog";

const promptSettings: PromptSettings = {
  context_size: 4096, max_tokens: 2048, thinking: true, tag_search_enabled: true,
  history_turns: 4, reasoning_level: "medium", provider: "local", chatgpt_model: "account-model",
};
const chatgpt: ChatGPTStatus = {
  connected: true, plan_enabled: true, active_account: "account", email: null,
  accounts: [], login_state: "idle", error_code: null, welcome_pending: false,
};

it.each(["local", "chatgpt"] as const)(
  "offers tag search above advanced options for %s and saves on close",
  async (provider) => {
    const user = userEvent.setup(), save = vi.fn(async () => {}), close = vi.fn();
    const saved = { ...promptSettings, provider };
    render(<SettingsDialog settings={generationSettings} imageModels={imageModels}
      promptSettings={saved} chatgpt={chatgpt} onSave={save} onClose={close} />);
    const search = screen.getByRole("checkbox", { name: "단보루 태그 검색" });
    expect(search).toHaveProperty("checked", true);
    expect(search.closest("details")).toBeNull();
    const advanced = screen.getByText("고급 설정").closest("details")!;
    expect(advanced.open).toBe(false);
    expect(search.compareDocumentPosition(advanced) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await user.click(search);
    expect(save).not.toHaveBeenCalled();
    await user.click(screen.getByText("닫기", { selector: "button" }));
    expect(save).toHaveBeenCalledWith(generationSettings, { ...saved, tag_search_enabled: false });
    expect(close).toHaveBeenCalledOnce();
  },
);

it("retains the tag search choice while switching prompt writers", async () => {
  const user = userEvent.setup(), save = vi.fn(async () => {});
  render(<SettingsDialog settings={generationSettings} imageModels={imageModels}
    promptSettings={promptSettings} chatgpt={chatgpt} onSave={save} onClose={vi.fn()} />);
  const search = screen.getByRole("checkbox", { name: "단보루 태그 검색" });
  await user.click(search);
  await user.selectOptions(screen.getByLabelText("프롬프트 작성 모델"), "chatgpt");
  expect(search).toHaveProperty("checked", false);
  await user.selectOptions(screen.getByLabelText("프롬프트 작성 모델"), "local");
  expect(search).toHaveProperty("checked", false);
  await user.keyboard("{Escape}");
  expect(save).toHaveBeenCalledWith(generationSettings, { ...promptSettings, tag_search_enabled: false });
});

it("disables tag search for FLUX without losing the Anima choice", async () => {
  const user = userEvent.setup();
  render(<SettingsDialog settings={generationSettings} imageModels={imageModels}
    promptSettings={promptSettings} onSave={vi.fn(async () => {})} onClose={vi.fn()} />);
  const search = screen.getByRole("checkbox", { name: "단보루 태그 검색" });
  await user.click(search);
  await user.selectOptions(screen.getByLabelText("모델"), "flux2");
  expect(search).toHaveProperty("disabled", true);
  expect(search).toHaveProperty("checked", false);
  await user.selectOptions(screen.getByLabelText("모델"), "anima");
  expect(search).toHaveProperty("disabled", false);
  expect(search).toHaveProperty("checked", false);
});
