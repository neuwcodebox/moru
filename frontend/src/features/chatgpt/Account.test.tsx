import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import Account from "./Account";
import type { ChatGPTStatus } from "../../api";

const disconnected: ChatGPTStatus = {
  connected: false, plan_enabled: false, active_account: null, email: null, accounts: [],
  login_state: "idle", error_code: null, welcome_pending: false,
};
const connected: ChatGPTStatus = {
  ...disconnected, connected: true, plan_enabled: true, active_account: "oaiapp_moru",
  email: "user@example.com", accounts: [{ id: "oaiapp_moru", email: "user@example.com", connected: true }],
};
const success = (value: unknown) => Promise.resolve({ ok: true as const, value });

beforeEach(() => {
  window.pywebview = { api: {
    get_chatgpt_models: vi.fn(() => success([
      { slug: "from-account", display_name: "Available GPT" },
    ])),
    login_chatgpt: vi.fn(() => success({ ...disconnected, login_state: "waiting" })),
    get_chatgpt_status: vi.fn(() => success(connected)),
    cancel_chatgpt_login: vi.fn(() => success(disconnected)),
    logout_chatgpt: vi.fn(() => success({ ...disconnected, revocation_confirmed: false })),
  } };
});

function AccountHarness({ initial = disconnected, disabled = false }: {
  initial?: ChatGPTStatus; disabled?: boolean;
}) {
  const [status, setStatus] = useState(initial);
  const [model, setModel] = useState("");
  return <Account status={status} model={model} disabled={disabled}
    onStatus={setStatus} onModel={setModel} />;
}

it("signs in through the bridge, polls status and displays the account's model catalog", async () => {
  render(<AccountHarness />);
  fireEvent.click(screen.getByRole("button", { name: "ChatGPT 로그인" }));
  await screen.findByText("연결됨");
  await screen.findByRole("option", { name: "Available GPT" });
  fireEvent.change(screen.getByLabelText("GPT 모델"), { target: { value: "from-account" } });
  expect((screen.getByLabelText("GPT 모델") as HTMLSelectElement).value).toBe("from-account");
  expect(window.pywebview?.api.login_chatgpt).toHaveBeenCalledWith(null);
  expect(screen.getByRole("link", { name: "사용량 관리" }).getAttribute("href"))
    .toBe("https://chatgpt.com/settings/usage");
  expect(screen.getByText(/요청·프롬프트·최근 대화 텍스트/)).toBeTruthy();
});

it("cancels a pending browser sign-in without requiring an account", async () => {
  window.pywebview!.api.get_chatgpt_status = vi.fn(() => new Promise<never>(() => {}));
  render(<AccountHarness initial={{ ...disconnected, login_state: "waiting" }} />);
  fireEvent.click(screen.getByRole("button", { name: "로그인 취소" }));
  await screen.findByText("연결되지 않음");
  expect(window.pywebview?.api.cancel_chatgpt_login).toHaveBeenCalledOnce();
});

it("shows missing plan permission without requesting a model catalog", async () => {
  render(<AccountHarness initial={{ ...connected, plan_enabled: false }} />);
  expect(screen.getByRole("alert").textContent).toContain("구독 사용 권한이 없습니다");
  expect(window.pywebview?.api.get_chatgpt_models).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "권한 허용" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "ChatGPT 로그인" })).toBeNull();
});

it("shows account management without offering sign-in again to an already connected account", async () => {
  render(<AccountHarness initial={connected} />);
  await screen.findByRole("option", { name: "Available GPT" });
  expect(screen.queryByRole("button", { name: "ChatGPT 로그인" })).toBeNull();
  expect(screen.queryByRole("button", { name: "다시 로그인" })).toBeNull();
  expect(screen.getByRole("button", { name: "계정 추가" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "로그아웃" })).toBeTruthy();
  expect(screen.getByLabelText("계정")).toHaveProperty("value", "oaiapp_moru");
  expect(screen.queryByRole("heading", { name: "ChatGPT" })).toBeNull();
});

it("offers reauthentication for a registered account whose local session ended", () => {
  render(<AccountHarness initial={{ ...connected, connected: false, plan_enabled: false }} />);
  fireEvent.click(screen.getByRole("button", { name: "다시 로그인" }));
  expect(window.pywebview?.api.login_chatgpt).toHaveBeenCalledWith("oaiapp_moru");
});

it("refreshes the model catalog with an accessible icon button beside the choice", async () => {
  render(<AccountHarness initial={connected} />);
  await screen.findByRole("option", { name: "Available GPT" });
  const refresh = screen.getByRole("button", { name: "모델 목록 새로고침" });
  await waitFor(() => expect(refresh).toHaveProperty("disabled", false));
  expect(refresh.textContent).toBe("");
  fireEvent.click(refresh);
  await waitFor(() => expect(window.pywebview?.api.get_chatgpt_models).toHaveBeenCalledTimes(2));
});

it("reports a model configuration save failure while keeping the previously selected model", async () => {
  window.pywebview!.api.get_chatgpt_models = vi.fn(() => success([
    { slug: "from-account", display_name: "Available GPT" },
    { slug: "other-model", display_name: "Other GPT" },
  ]));
  const save = vi.fn(async () => { throw { code: "DATABASE_FAILED" }; });
  render(<Account status={connected} model="from-account" onModel={save} onStatus={vi.fn()} />);
  await screen.findByRole("option", { name: "Other GPT" });
  fireEvent.change(screen.getByLabelText("GPT 모델"), { target: { value: "other-model" } });
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "작업 기록을 저장하거나 불러올 수 없습니다.");
  expect(screen.getByLabelText("GPT 모델")).toHaveProperty("value", "from-account");
});

it("reports an unavailable saved model without silently replacing the configuration", async () => {
  const save = vi.fn();
  render(<Account status={connected} model="unavailable" onModel={save} onStatus={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent",
    "이 계정에서 사용할 수 없는 모델입니다. 다른 모델을 선택하세요.");
  expect(screen.getByLabelText("GPT 모델")).toHaveProperty("value", "unavailable");
  expect(save).not.toHaveBeenCalled();
});

it("reports that remote revocation was not confirmed after clearing local credentials", async () => {
  render(<AccountHarness initial={connected} />);
  fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("원격 세션 해제"));
  expect(screen.getByText("연결되지 않음")).toBeTruthy();
});

it("keeps authentication errors visible without exposing raw backend text", async () => {
  window.pywebview!.api.login_chatgpt = vi.fn(() => Promise.resolve({
    ok: false as const, error: { code: "CHATGPT_AUTH_FAILED", message: "private token" },
  }));
  render(<AccountHarness />);
  fireEvent.click(screen.getByRole("button", { name: "ChatGPT 로그인" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("로그인에 실패"));
  expect(screen.queryByText("private token")).toBeNull();
});

it("prevents account changes during generation", () => {
  render(<AccountHarness initial={connected} disabled />);
  expect((screen.getByRole("button", { name: "로그아웃" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "계정 추가" }) as HTMLButtonElement).disabled).toBe(true);
});
