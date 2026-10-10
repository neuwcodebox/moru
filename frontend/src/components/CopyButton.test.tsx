import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import CopyButton from "./CopyButton";

afterEach(() => vi.useRealTimers());

it("confirms copying inside the button and restores the copy action without adding a message panel", async () => {
  vi.useFakeTimers();
  const copy = vi.fn().mockResolvedValue(undefined);
  render(<CopyButton onCopy={copy} onError={vi.fn()} />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "복사" })); });
  expect(copy).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "복사 완료" })).toBeTruthy();
  expect(screen.getByRole("status").textContent).toBeTruthy();
  await act(async () => { await vi.advanceTimersToNextTimerAsync(); });
  expect(screen.getByRole("button", { name: "복사" })).toBeTruthy();
  expect(screen.getByRole("status").textContent).toBe("");
});

it("reports copy failure and makes the action available to retry", async () => {
  const error = vi.fn();
  const copy = vi.fn().mockRejectedValueOnce(new Error("복사 실패")).mockResolvedValue(undefined);
  render(<CopyButton onCopy={copy} onError={error} />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "복사" })); });
  expect(error).toHaveBeenCalledWith(expect.objectContaining({ message: "복사 실패" }));
  expect(screen.getByRole("button", { name: "복사" }).hasAttribute("disabled")).toBe(false);
  expect(screen.queryByRole("button", { name: "복사 완료" })).toBeNull();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "복사" })); });
  expect(copy).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "복사 완료" })).toBeTruthy();
});
