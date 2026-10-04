import { afterEach, describe, expect, it } from "vitest";
import { BridgeError } from "./api";
import { errorMessage } from "./errorMessages";
import i18n from "./i18n";

afterEach(async () => {
  await i18n.changeLanguage("ko");
});

describe("localized errors", () => {
  it("retranslates an existing bridge failure after changing the language", async () => {
    const error = new BridgeError("INVALID_SETTINGS");
    await i18n.changeLanguage("ko");
    expect(errorMessage(error)).toBe("생성 설정을 확인해 주세요.");
    await i18n.changeLanguage("en");
    expect(errorMessage(error)).toBe("Please check the generation settings.");
  });

  it.each(["GENERATION_INTERRUPTED", "CUDA_OOM", "MODEL_DOWNLOAD_FAILED"])(
    "uses the code rather than a stale server message for %s",
    async (code) => {
      await i18n.changeLanguage("en");
      const error = { error_code: code, message: "이전 언어 오류" };
      expect(errorMessage(error)).toBe(i18n.t(code, { ns: "errors" }));
      expect(errorMessage(error)).not.toContain("이전 언어");
    },
  );

  it("gives unknown codes a localized safe fallback", async () => {
    await i18n.changeLanguage("en");
    expect(errorMessage({ error_code: "NEW_BACKEND_ERROR", message: "/private/path" }))
      .toBe("Could not complete the request. Please try again.");
    expect(errorMessage(new BridgeError("NEW_BACKEND_ERROR"), "IMAGE_LOAD_FAILED"))
      .toBe("Could not load the image.");
  });

  it("preserves deliberately authored local error messages", () => {
    expect(errorMessage(new Error("Specific local validation error")))
      .toBe("Specific local validation error");
  });

  it("uses the requested fallback for non-error exceptions without exposing their contents", async () => {
    await i18n.changeLanguage("en");
    expect(errorMessage("/private/path", "COPY_FAILED"))
      .toBe("Could not copy. Please try again.");
  });
});
