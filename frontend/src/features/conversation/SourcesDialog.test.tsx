import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import SourcesDialog from "./SourcesDialog";

it("shows readable lookup inputs and reference results instead of raw tool payloads", async () => {
  const user = userEvent.setup();
  render(<SourcesDialog sources={[
    { tool: "search_tags", query: "arms crossed", result: ["crossed_arms"] },
    { tool: "get_tag_info", query: "gray_hair", result: {
      name: "grey_hair", description: "Grey-colored hair.",
    } },
    { tool: "get_related_tags", query: "grey_hair", result: {
      cooccurring: ["long_hair"], wiki_links: ["white_hair"],
    } },
  ]} onClose={vi.fn()} />);
  const dialog = screen.getByRole("dialog", { name: "소스" });
  expect(within(dialog).getByText("arms crossed")).toBeTruthy();
  expect(within(dialog).getByText("gray_hair")).toBeTruthy();
  expect(within(dialog).getByText("Grey-colored hair.")).toBeTruthy();
  expect(within(dialog).getByRole("link", { name: "crossed_arms" }).getAttribute("href"))
    .toBe("https://safebooru.donmai.us/wiki_pages/crossed_arms");
  const cooccurring = within(dialog).getByRole("group", { name: "공출현 태그" });
  const referenced = within(dialog).getByRole("group", { name: "Wiki 참조 태그" });
  expect(cooccurring).toHaveProperty("open", false);
  expect(referenced).toHaveProperty("open", false);
  await user.click(within(cooccurring).getByText("공출현 태그 (1)"));
  expect(cooccurring).toHaveProperty("open", true);
  expect(referenced).toHaveProperty("open", false);
  expect(within(cooccurring).getByRole("link", { name: "long_hair" })).toBeTruthy();
  await user.click(within(referenced).getByText("Wiki 참조 태그 (1)"));
  expect(within(referenced).getByRole("link", { name: "white_hair" })).toBeTruthy();
  expect(dialog.textContent).not.toContain("function_call");
});

it("shows related tag counts without rendering empty sections", () => {
  render(<SourcesDialog sources={[
    { tool: "get_related_tags", query: "grey_hair", result: {
      cooccurring: Array.from({ length: 20 }, (_, index) => `related_${index}`), wiki_links: [],
    } },
    { tool: "get_related_tags", query: "missing", result: { cooccurring: [], wiki_links: [] } },
  ]} onClose={vi.fn()} />);
  expect(screen.getByText("공출현 태그 (20)")).toBeTruthy();
  expect(screen.getByRole("group", { name: "공출현 태그" })).toHaveProperty("open", false);
  expect(screen.queryByRole("group", { name: "Wiki 참조 태그" })).toBeNull();
  expect(screen.getByText("검색 결과가 없습니다.")).toBeTruthy();
});

it("keeps wiki bodies collapsed until each is opened", async () => {
  const user = userEvent.setup();
  render(<SourcesDialog sources={[
    { tool: "get_tag_info", query: "grey_hair", result: {
      name: "grey_hair", description: "Grey-colored hair.",
    } },
    { tool: "get_tag_info", query: "silver_hair", result: {
      name: null, description: "Use grey_hair or white_hair.",
    } },
  ]} onClose={vi.fn()} />);
  const summaries = screen.getAllByText("위키 본문");
  const bodies = summaries.map((summary) => summary.closest("details")!);
  expect(bodies.map((body) => body.open)).toEqual([false, false]);
  expect(screen.getByRole("link", { name: "grey_hair" })).toBeTruthy();

  await user.click(summaries[0]);
  expect(bodies.map((body) => body.open)).toEqual([true, false]);
  await user.click(summaries[1]);
  expect(bodies.map((body) => body.open)).toEqual([true, true]);
  await user.click(summaries[0]);
  expect(bodies.map((body) => body.open)).toEqual([false, true]);
});

it("distinguishes an unavailable lookup from an empty result and a deprecated tag", () => {
  render(<SourcesDialog sources={[
    { tool: "search_tags", query: "missing", result: [] },
    { tool: "get_tag_info", query: "old_tag", result: {
      name: "old_tag", description: null, deprecated: true,
    } },
    { tool: "get_related_tags", query: "grey_hair", result: { error: "lookup_unavailable" } },
  ]} onClose={vi.fn()} />);
  expect(screen.getByText("검색 결과가 없습니다.")).toBeTruthy();
  expect(screen.getByText("사용 중단된 태그")).toBeTruthy();
  expect(screen.getByText("조회하지 못했습니다.")).toBeTruthy();
  expect(screen.queryByText("위키 본문")).toBeNull();
});

it("shows wiki-only guidance without claiming a verified canonical tag", () => {
  render(<SourcesDialog sources={[
    { tool: "get_tag_info", query: "silver_hair", result: {
      name: null, description: "Use grey_hair or white_hair.",
    } },
  ]} onClose={vi.fn()} />);
  expect(screen.getByText("Use grey_hair or white_hair.")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "silver_hair" })).toBeNull();
});

it("old images with no saved references show an empty state and close normally", async () => {
  const user = userEvent.setup(), close = vi.fn();
  render(<SourcesDialog sources={[]} onClose={close} />);
  expect(screen.getByText("저장된 참고 정보가 없습니다.")).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(close).toHaveBeenCalledOnce();
});

it("reference text is rendered as text rather than executable HTML", () => {
  const { container } = render(<SourcesDialog sources={[
    { tool: "get_tag_info", query: "grey_hair", result: {
      name: "grey_hair", description: '<img src=x onerror="alert(1)">',
    } },
  ]} onClose={vi.fn()} />);
  expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeTruthy();
  expect(container.querySelector("img")).toBeNull();
});
