import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import CopyButton from "./CopyButton";

afterEach(() => vi.useRealTimers());

it("confirms copying inside the button and restores the copy action without adding a message panel", async () => {
  vi.useFakeTimers();
  const copy = vi.fn().mockResolvedValue(undefined);
  const { container } = render(<CopyButton onCopy={copy} onError={vi.fn()} />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "복사" })); });
  expect(copy).toHaveBeenCalledOnce();
  const confirmed = screen.getByRole("button", { name: "복사 완료" });
  expect(confirmed.querySelector(".lucide-check")).toBeTruthy();
  expect(container.querySelector("p")).toBeNull();
  await act(async () => { vi.advanceTimersByTime(1600); });
  expect(screen.getByRole("button", { name: "복사" }).querySelector(".lucide-copy")).toBeTruthy();
});

it("reports copy failure and makes the action available to retry", async () => {
  const error = vi.fn();
  render(<CopyButton onCopy={vi.fn().mockRejectedValue(new Error("복사 실패"))} onError={error} />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "복사" })); });
  expect(error).toHaveBeenCalledWith("복사 실패");
  expect(screen.getByRole("button", { name: "복사" }).hasAttribute("disabled")).toBe(false);
  expect(screen.queryByRole("button", { name: "복사 완료" })).toBeNull();
});
