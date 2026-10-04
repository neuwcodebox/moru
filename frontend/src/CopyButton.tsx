import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { Check, Copy, LoaderCircle } from "lucide-react";

export default function CopyButton({
  onCopy,
  onError,
  disabled = false,
}: {
  onCopy: () => Promise<void>;
  onError: (error: unknown) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState<"idle" | "pending" | "copied">("idle");
  useEffect(() => {
    if (state !== "copied") return;
    const timer = setTimeout(() => setState("idle"), 1600);
    return () => clearTimeout(timer);
  }, [state]);
  return (
    <button
      type="button"
      className={`copy-button ${state}`}
      aria-label={state === "copied" ? t("copied") : t("copy")}
      title={state === "copied" ? t("copyNotice") : t("copy")}
      disabled={disabled || state === "pending"}
      onClick={async () => {
        setState("pending");
        try {
          await onCopy();
          setState("copied");
        } catch (error) {
          setState("idle");
          onError(error ?? { code: "COPY_FAILED" });
        }
      }}
    >
      <span className="copy-symbol" key={state} aria-hidden="true">
        {state === "copied" ? <Check size={15} /> : state === "pending"
          ? <LoaderCircle size={15} className="spinner" /> : <Copy size={15} />}
      </span>
      {t("copy")}
      <span className="sr-only" role="status">
        {state === "copied" ? t("copyNotice") : ""}
      </span>
    </button>
  );
}
