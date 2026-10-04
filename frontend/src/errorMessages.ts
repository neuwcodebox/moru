import { BridgeError } from "./api";
import i18n from "./i18n";

/** Translate boundary errors when rendering, including errors saved before a language change. */
export function errorMessage(error: unknown, fallbackCode = "UNKNOWN_ERROR"): string {
  let code: unknown;
  if (typeof error === "object" && error !== null) {
    if ("code" in error) code = error.code;
    else if ("error_code" in error) code = error.error_code;
  }
  if (typeof code === "string") {
    return i18n.t([code, fallbackCode, "UNKNOWN_ERROR"], { ns: "errors" });
  }
  // Local, deliberately authored errors remain useful; server messages are never used.
  if (error instanceof Error && !(error instanceof BridgeError)) return error.message;
  return i18n.t([fallbackCode, "UNKNOWN_ERROR"], { ns: "errors" });
}
