import { expect, it } from "vitest";
import i18n from "./i18n";
import { BridgeError, call } from "./api";
import { errorMessage } from "./errorMessages";

it("falls back to English when a Korean translation is unavailable", async () => {
  i18n.addResource("en", "translation", "fallbackExample", "English fallback");
  try {
    expect(i18n.t("fallbackExample")).toBe("English fallback");
  } finally {
    delete i18n.getResourceBundle("en", "translation").fallbackExample;
  }
});

it("translates the same existing error in the newly selected language", async () => {
  const error = new BridgeError("CUDA_OOM");
  expect(errorMessage(error)).toBe("GPU 메모리가 부족합니다. 이미지 크기를 줄여 주세요.");
  await i18n.changeLanguage("en");
  expect(errorMessage(error)).toBe("There is not enough GPU memory. Please reduce the image size.");
  expect(errorMessage({ error_code: "UNRECOGNIZED", message: "private backend path" })).toBe("Could not complete the request. Please try again.");
});

it("reports a disconnected desktop bridge without exposing raw diagnostics", async () => {
  window.pywebview = undefined;
  await expect(call("bootstrap")).rejects.toMatchObject({ code: "DESKTOP_UNAVAILABLE" });
});
