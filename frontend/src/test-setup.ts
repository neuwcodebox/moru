import i18n from "./i18n";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

Object.defineProperty(HTMLElement.prototype, "scrollTo", {
  configurable: true,
  value(this: HTMLElement, options: ScrollToOptions) {
    if (options.top != null) this.scrollTop = options.top;
    if (options.left != null) this.scrollLeft = options.left;
  },
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.pywebview;
});

beforeEach(async () => { await i18n.changeLanguage("ko"); });
