import i18n from "./i18n";
import { beforeEach } from "vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

Object.defineProperty(HTMLElement.prototype, "scrollTo", {
  configurable: true,
  value(this: HTMLElement, options: ScrollToOptions) {
    if (options.top != null) this.scrollTop = options.top;
    if (options.left != null) this.scrollLeft = options.left;
  },
});

afterEach(cleanup);

beforeEach(async () => { await i18n.changeLanguage("ko"); });
