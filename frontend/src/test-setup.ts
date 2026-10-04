import i18n from "./i18n";
import { beforeEach } from "vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(cleanup);

beforeEach(async () => { await i18n.changeLanguage("ko"); });
